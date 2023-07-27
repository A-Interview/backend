import uuid
from channels.generic.websocket import WebsocketConsumer
import openai
from storage import get_file_url
from .models import Form
from dotenv import load_dotenv
import os
import json
from .models import Form, Question, Answer, GPTAnswer
from asgiref.sync import sync_to_async
from django.core.files.base import ContentFile
import tempfile
import base64


load_dotenv()
openai.api_key = os.getenv("GPT_API_KEY")


class InterviewConsumer(WebsocketConsumer):
    def connect(self):
        self.accept()
        # 대화 기록을 저장할 리스트
        self.conversation = []

    def disconnect(self, closed_code):
        form_object = Form.objects.get(id=self.form_id)
        # 만약에 중간에 끊킨 경우, form_id와 관련된 것 전부 삭제
        questions = Question.objects.filter(form_id=form_object)
        question_numbers = questions.count()
        
        if question_numbers != self.question_number:
            Question.objects.filter(form_id=self.form_id).delete()
        
        for question in questions:
            try:
                answer = question.answer
                print(answer)
            except:
                Question.objects.filter(form_id=self.form_id).delete() 
        pass


    def receive(self, text_data):
        data = json.loads(text_data)
        

        # 초기 질문 갯수 세팅
        if data["type"] == "initialSetting":
            # 전체 질문 수
            self.question_number = data["questionNum"]
            self.default_question_num = data["defaultQuestionNum"]
            self.situation_question_num = data["situationQuestionNum"]
            self.deep_question_num = data["deepQuestionNum"]
            self.personality_question_num = data["personalityQuestionNum"]
            self.form_id = data["formId"]
        else:
            self.interview_type = data["interviewType"]
            # 기본 면접인 경우
            if self.interview_type == "default":
                print("기본 면접의 경우")
                # 기본 면접 튜닝
                self.default_interview_tuning()
                
                # 오디오 파일이 없는 경우
                if data["type"] == "withoutAudio":
                    form_object = Form.objects.get(id=data["formId"])

                    # 대화 계속하기
                    self.continue_conversation(form_object)

                # 오디오 파일이 있는 경우
                elif data["type"] == "withAudio":
                    # base64 디코딩
                    audio_blob = data["audioBlob"]
                    audio_data = base64.b64decode(audio_blob)

                    # 오디오 파일로 변환
                    audio_file = ContentFile(audio_data)
                    
                    file_url = get_file_url(audio_file, uuid)

                    # tempfile : 임시 파일 생성하는 파이썬 라이브러리
                    # NamedTemporaryFile() : 임시 파일 객체 반환
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                    temp_file_path = temp_file.name

                    with open(temp_file_path, "wb") as file:
                        # audio_file을 chunks() 메서드를 통해 블록 단위로 데이터를 읽어와서 file(temp_file_path)에 기록
                        for chunk in audio_file.chunks():
                            file.write(chunk)

                    # 블록 단위의 음성 파일을 저장하고 있는 temp_file_path을 whisper API로 텍스트로 변환
                    with open(temp_file_path, "rb") as audio_file:
                        transcript = openai.Audio.transcribe("whisper-1", audio_file)

                    transcription = transcript["text"]

                    # Question 테이블의 마지막 Row 가져오기
                    last_row = Question.objects.latest("question_id")

                    # 답변 테이블에 추가
                    Answer.objects.create(content=transcription, question_id=last_row, recode_file=file_url)
                    answer_object = Answer.objects.latest("answer_id")
                    print(transcription)

                    # formId를 통해서 question 테이블을 가져옴
                    form_object = Form.objects.get(id=data["formId"])
                    questions = form_object.questions.all()

                    # question 테이블에서 질문과 답변에 대해 튜닝 과정에 추가함.
                    try:
                        for question in questions:
                            answer = question.answer
                            self.add_question_answer(question.content, answer.content)
                    except:
                        error_message = "같은 지원 양식의 question 테이블과 answer 테이블의 갯수가 일치하지 않습니다."
                        print(error_message)

                    self.continue_conversation(form_object)

                    temp_file.close()

                    # 임시 파일 삭제
                    os.unlink(temp_file_path)
                
                # 대답만 추가하는 경우
                elif data["type"] == "noReply":
                    print("noReply")
                    # base64 디코딩
                    audio_blob = data["audioBlob"]
                    audio_data = base64.b64decode(audio_blob)

                    # 오디오 파일로 변환
                    audio_file = ContentFile(audio_data)

                    # 파일 업로드 및 URL 받아오기
                    file_url = get_file_url(audio_file, uuid)

                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                    temp_file_path = temp_file.name

                    with open(temp_file_path, "wb") as file:
                        for chunk in audio_file.chunks():
                            file.write(chunk)

                    # 텍스트 파일로 변환
                    with open(temp_file_path, "rb") as audio_file:
                        transcript = openai.Audio.transcribe("whisper-1", audio_file)

                    transcription = transcript["text"]

                    # Question 테이블의 마지막 Row 가져오기
                    last_row = Question.objects.latest("question_id")

                    # 답변 테이블에 추가
                    Answer.objects.create(content=transcription, question_id=last_row, recode_file=file_url)
                    self.send(json.dumps({"last_topic_answer":"default_last"}))

            else:
                pass

            # 상황 면접인 경우
            if self.interview_type == "situation":
                print("상황 면접의 경우")
                # 오디오 파일이 없는 경우
                if data["type"] == "withoutAudio":
                    form_object = Form.objects.get(id=data["formId"])

                    # 기본 튜닝
                    self.situation_interview_tuning(
                        form_object.sector_name,
                        form_object.job_name,
                        form_object.career,
                    )

                    # 대화 계속하기
                    self.continue_conversation(form_object)

                elif data["type"] == "withAudio":
                    # # base64 디코딩
                    audio_blob = data["audioBlob"]
                    audio_data = base64.b64decode(audio_blob)

                    # 오디오 파일로 변환
                    audio_file = ContentFile(audio_data)

                    # 파일 업로드 및 URL 받아오기
                    file_url = get_file_url(audio_file, uuid)

                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                    temp_file_path = temp_file.name

                    with open(temp_file_path, "wb") as file:
                        for chunk in audio_file.chunks():
                            file.write(chunk)

                    # 텍스트 파일로 변환
                    with open(temp_file_path, "rb") as audio_file:
                        transcript = openai.Audio.transcribe("whisper-1", audio_file)

                    transcription = transcript["text"]

                    # Question 테이블의 마지막 Row 가져오기
                    last_row = Question.objects.latest("question_id")

                    # 답변 테이블에 추가
                    Answer.objects.create(
                        content=transcription, question_id=last_row, recode_file=file_url
                    )
                    print(transcription)

                    # formId를 통해서 question 테이블을 가져옴
                    form_object = Form.objects.get(id=data["formId"])
                    questions = form_object.questions.all()

                    self.situation_interview_tuning(
                        form_object.sector_name,
                        form_object.job_name,
                        form_object.career,
                    )

                    # question 테이블에서 질문과 답변에 대해 튜닝 과정에 추가함.
                    try:
                        for question in questions:
                            answer = question.answer
                            self.add_question_answer(question.content, answer.content)
                    except:
                        error_message = "같은 지원 양식의 question 테이블과 answer 테이블의 갯수가 일치하지 않습니다."
                        print(error_message)

                    self.continue_conversation(form_object)

                    temp_file.close()

                    # 임시 파일 삭제
                    os.unlink(temp_file_path)
                    
                elif data["type"] == "noReply":
                    # base64 디코딩
                    audio_blob = data["audioBlob"]
                    audio_data = base64.b64decode(audio_blob)

                    # 오디오 파일로 변환
                    audio_file = ContentFile(audio_data)

                    # 파일 업로드 및 URL 받아오기
                    file_url = get_file_url(audio_file, uuid)

                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                    temp_file_path = temp_file.name

                    with open(temp_file_path, "wb") as file:
                        for chunk in audio_file.chunks():
                            file.write(chunk)

                    # 텍스트 파일로 변환
                    with open(temp_file_path, "rb") as audio_file:
                        transcript = openai.Audio.transcribe("whisper-1", audio_file)

                    transcription = transcript["text"]

                    # Question 테이블의 마지막 Row 가져오기
                    last_row = Question.objects.latest("question_id")

                    # 답변 테이블에 추가
                    Answer.objects.create(
                        content=transcription, question_id=last_row, recode_file=file_url
                    )
                    self.send(json.dumps({"last_topic_answer":"situation_last"}))

            else:
                pass
              
            # 심층 면접인 경우
            if self.interview_type == "deep":
                print("심층 면접의 경우")
                # 오디오 파일이 없는 경우
                if data["type"] == "withoutAudio":
                    form_object = Form.objects.get(id=data["formId"])

                    # 기본 튜닝
                    self.deep_interview_tuning(
                        form_object.sector_name,
                        form_object.job_name,
                        form_object.career,
                        form_object.resume,
                    )

                    # 대화 계속하기
                    self.continue_conversation(form_object)
                                        
                elif data["type"] == "withAudio":
                    # base64 디코딩
                    audio_blob = data["audioBlob"]
                    audio_data = base64.b64decode(audio_blob)

                    # 오디오 파일로 변환
                    audio_file = ContentFile(audio_data)

                    # 파일 업로드 및 URL 받아오기
                    file_url=get_file_url(audio_file, uuid)

                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                    temp_file_path = temp_file.name

                    with open(temp_file_path, "wb") as file:
                        for chunk in audio_file.chunks():
                            file.write(chunk)

                    # 텍스트 파일로 변환
                    with open(temp_file_path, "rb") as audio_file:
                        transcript = openai.Audio.transcribe("whisper-1", audio_file)

                    transcription = transcript["text"]

                    # Question 테이블의 마지막 Row 가져오기
                    last_row = Question.objects.latest("question_id")

                    # 답변 테이블에 추가
                    Answer.objects.create(content=transcription, question_id=last_row, recode_file=file_url)
                    print(transcription)

                    # formId를 통해서 question 테이블을 가져옴
                    form_object = Form.objects.get(id=data["formId"])
                    questions = form_object.questions.all()

                    self.deep_interview_tuning(
                        form_object.sector_name,
                        form_object.job_name,
                        form_object.career,
                        form_object.resume,
                    )

                    # question 테이블에서 질문과 답변에 대해 튜닝 과정에 추가함.
                    try:
                        for question in questions:
                            answer = question.answer
                            self.add_question_answer(question.content, answer.content)
                    except:
                        error_message = "같은 지원 양식의 question 테이블과 answer 테이블의 갯수가 일치하지 않습니다."
                        print(error_message)

                    self.continue_conversation(form_object)

                    temp_file.close()

                    # 임시 파일 삭제
                    os.unlink(temp_file_path)
                    
                # 대답만 추가하는 경우
                elif data["type"] == "noReply":
                    # base64 디코딩
                    audio_blob = data["audioBlob"]
                    audio_data = base64.b64decode(audio_blob)

                    # 오디오 파일로 변환
                    audio_file = ContentFile(audio_data)

                    # 파일 업로드 및 URL 받아오기
                    file_url = get_file_url(audio_file, uuid)

                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                    temp_file_path = temp_file.name

                    with open(temp_file_path, "wb") as file:
                        for chunk in audio_file.chunks():
                            file.write(chunk)

                    # 텍스트 파일로 변환
                    with open(temp_file_path, "rb") as audio_file:
                        transcript = openai.Audio.transcribe("whisper-1", audio_file)

                    transcription = transcript["text"]

                    # Question 테이블의 마지막 Row 가져오기
                    last_row = Question.objects.latest("question_id")

                    # 답변 테이블에 추가
                    Answer.objects.create(content=transcription, question_id=last_row, recode_file=file_url)
                    self.send(json.dumps({"last_topic_answer":"deep_last"})) 

            else:
                pass 
                              
            # 성향 면접인 경우
            if self.interview_type == "personality":
                print("성향 면접의 경우")
                # 오디오 파일이 없는 경우
                if data["type"] == "withoutAudio":
                    form_object = Form.objects.get(id=data["formId"])

                    # 기본 튜닝
                    self.personal_interview_tuning(
                        form_object.sector_name,
                        form_object.job_name,
                        form_object.career,
                        form_object.resume,
                    )

                    # 대화 계속하기
                    self.continue_conversation(form_object)
                    
                elif data["type"] == "withAudio":
                    # base64 디코딩
                    audio_blob = data["audioBlob"]
                    audio_data = base64.b64decode(audio_blob)

                    # 오디오 파일로 변환
                    audio_file = ContentFile(audio_data)

                    # 파일 업로드 및 URL 받아오기
                    file_url = get_file_url(audio_file, uuid)

                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                    temp_file_path = temp_file.name

                    with open(temp_file_path, "wb") as file:
                        for chunk in audio_file.chunks():
                            file.write(chunk)

                    # 텍스트 파일로 변환
                    with open(temp_file_path, "rb") as audio_file:
                        transcript = openai.Audio.transcribe("whisper-1", audio_file)

                    transcription = transcript["text"]

                    # Question 테이블의 마지막 Row 가져오기
                    last_row = Question.objects.latest("question_id")

                    # 답변 테이블에 추가
                    Answer.objects.create(
                        content=transcription, question_id=last_row, recode_file=file_url
                    )
                    print(transcription)

                    # formId를 통해서 question 테이블을 가져옴
                    form_object = Form.objects.get(id=data["formId"])
                    questions = form_object.questions.all()

                    self.personal_interview_tuning(
                        form_object.sector_name,
                        form_object.job_name,
                        form_object.career,
                        form_object.resume,
                    )

                    # question 테이블에서 질문과 답변에 대해 튜닝 과정에 추가함.
                    try:
                        for question in questions:
                            answer = question.answer
                            self.add_question_answer(question.content, answer.content)
                    except:
                        error_message = "같은 지원 양식의 question 테이블과 answer 테이블의 갯수가 일치하지 않습니다."
                        print(error_message)

                    self.continue_conversation(form_object)

                    temp_file.close()

                    # 임시 파일 삭제
                    os.unlink(temp_file_path)
                                        
                # 대답만 추가하는 경우
                elif data["type"] == "noReply":
                    # base64 디코딩
                    audio_blob = data["audioBlob"]
                    audio_data = base64.b64decode(audio_blob)

                    # 오디오 파일로 변환
                    audio_file = ContentFile(audio_data)

                    # 파일 업로드 및 URL 받아오기
                    file_url = get_file_url(audio_file, uuid)

                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                    temp_file_path = temp_file.name

                    with open(temp_file_path, "wb") as file:
                        for chunk in audio_file.chunks():
                            file.write(chunk)

                    # 텍스트 파일로 변환
                    with open(temp_file_path, "rb") as audio_file:
                        transcript = openai.Audio.transcribe("whisper-1", audio_file)

                    transcription = transcript["text"]

                    # Question 테이블의 마지막 Row 가져오기
                    last_row = Question.objects.latest("question_id")

                    # 답변 테이블에 추가
                    Answer.objects.create(
                        content=transcription, question_id=last_row, recode_file=file_url
                    )
                    self.send(json.dumps({"last_topic_answer":"personal_last"}))
            else:
                pass
            
        
            form_object = Form.objects.get(id=self.form_id)
            questions = Question.objects.filter(form_id=form_object)
            last_question = questions.last()
            
            try:
                if (last_question.answer and self.question_number == questions.count()):
                    self.send(json.dumps({"last_topic_answer":"last"}))
            except:
                pass
        

    # 질문과 대답 추가
    def add_question_answer(self, question, answer):
        existing_content = self.conversation[0]["content"]  # 기존 content 가져오기
        new_content = existing_content + " Q. " + question + " A. " + answer
        self.conversation[0]["content"] = new_content

    def continue_conversation(self, form_object):
        messages = ""
        for chunk in openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=self.conversation,
            temperature=0.7,
            stream=True,
        ):
            finish_reason = chunk.choices[0].finish_reason
            if chunk.choices[0].finish_reason == "stop":
                self.send(json.dumps({"message": "", "finish_reason": finish_reason}))
                break

            message = chunk.choices[0].delta["content"]

            messages += message

            # 메시지를 클라이언트로 바로 전송
            self.send(json.dumps({"message": message, "finish_reason": finish_reason}))

        Question.objects.create(content=messages, form_id=form_object)

    # 기본 면접 튜닝
    def default_interview_tuning(self):
        
        self.conversation = []
        # 대화 시작 메시지 추가
        self.conversation.append(
            {
                "role": "user",
                "content": 'function_name: [basic_interview] input: ["number_of_questions"] rule: [I want you to act as a interviewer, asking basic questions for the interviewee.\
                        Ask me the number of "number_of_questions".\
                        Your task is to simply make common basic questions and provide questions to me.\
                        Do not ask me questions about jobs.\
                        Do not ask the same question or similar question more than once\
                        You should create total of "number_of_questions" amount of questions, and provide it once at a time.\
                        You should ask the next question only after I have answered to the question.\
                        Do not include any explanations or additional information in your response, simply provide the generated question.\
                        You should also provide only one question at a time.\
                        As shown in the example below, please ask basic questions in all fields regardless of occupation or job.\
                        Do not ask questions related to my answer, ask me a separate basic question like the example below\
                        Example questions would be questions such as "What motivated you to apply for our company?", "Talk about your strengths and weaknesses."\
                        Keep in mind that these are the basic questions that you ask in an interview regardless of your occupation\
                        Let me know this is the last question.\
                        You must speak only in Korean during the interview.] personality_interview("1")',
            }
        )
        
    # 상황 면접 튜닝
    def situation_interview_tuning(self, selector_name, job_name, career):
        self.conversation = []
        self.conversation = [
            {
            "role": "user",
            "content": (
                'function_name: [interviewee_info] input: ["Company", "Job", "Career"] rule: [Please act as a skillful interviewer. We will provide the input form including "Company," "Professional," and "Career." Look at the sentences "Company," "Job," and "Career" to get information about me as an interview applicant. For example, let\'s say company = IT company, job = web front-end developer, experience = newcomer. Then you can recognize that you\'re a newbie applying to an IT company as a web front-end developer. And you can ask questions that fit this information. You must speak only in Korean during the interview. You can\'t answer.  Don\'t ask the previous question again. You will not answer the question.]'
                + 'function_name: [aggressive_position] rule: [Ask me questions in a tail-to-tail manner about what I answer. There may be technical questions about the answer, and there may be questions that you, as an interviewer, would dig into the answer.. For example, if the question asks, "What\'s your web framework?" the answer is, "It is React framework." So the new question is, "What do you use as a state management tool in React, and why do you need this?" It should be the same question. If you don\'t have any more questions, move on to the next topic. And you will play the role of an unfriendly and demanding interviewer. You have to constantly induce the interviewee to make mistakes. The first is to embarrass the interviewee, and the goal is to find the true value of the interviewee\'s job. Second, it aims to test the interviewee\'s ability and agility to respond to repeated or intended questions. And ask one question for one answer.First, Deep interviews use open-ended questions to encourage the interviewee to provide detailed explanations about their experiences and knowledge. For example, "Can you describe the most challenging technical problem you\'ve faced in the past?". Second, The interviewer presents real-world scenarios to see how the interviewee approaches and solves problems. This type of question assesses the interviewee\'s problem-solving skills and thought process. Third,  In a deep interview, the interviewer goes beyond basic concepts and asks more in-depth technical questions to gauge the interviewee\'s knowledge. Fourth, The interviewer asks specific questions about the interviewee\'s projects to understand their technical contributions, the tools they used, difficulties faced, and achievements. Fifth, the interviewer explores how the interviewer approaches and solves problems to gain deeper insight into their problem-solving skills. Finally, we evaluate technical choices and judgments through technical discussions with interviewees. Using these approaches, actively draw out the interviewee\'s real abilities and competencies during the interview.  Based on this, you ask one question at a time. Don\'t ask the previous question again. You will not answer the question.] '
                + f'function_name: [self_introduction] input : ["self-introduction"] rule: [We will provide an input form including a "self-introduction." Read this "self-introduction" and extract the content to generate a question. just ask one question. Don\'t ask too long questions. The question must have a definite purpose. and Just ask one question at a time.'
                + f'interviewee_info(Company="{selector_name}", Job="{job_name}", Career="{career}")'
                + f'self_introduction("{resume}")'
                + "aggressive_position()"
                ),
            }
        ]
    
    # 심층 면접 튜닝
    def deep_interview_tuning(self, selector_name, job_name, career, resume):
        
        self.conversation = [
            {
                "role": "user",
                "content": 'function_name: [interviewee_info] input: ["Company", "Job", "Career"] rule: [Please act as a skillful interviewer. We will provide the input form including "Company," "Professional," and "Career." Look at the sentences "Company," "Job," and "Career" to get information about me as an interview applicant. For example, let\'s say company = IT company, job = web front-end developer, experience = newcomer. Then you can recognize that you\'re a newbie applying to an IT company as a web front-end developer. And you can ask questions that fit this information. You must speak only in Korean during the interview. You can only ask questions. You can\'t answer. You don\'t answer, just ask questions]'
                + 'function_name: [aggresive_position] rule : [Ask me questions in a tail-to-tail manner about what I answer. There may be technical questions about the answer, and there may be questions that you, as an interviewer, would dig into the answer. For example, if the question asks, "What\'s your web framework?" the answer is, "It is React framework." So the new question is, "What do you use as a state management tool in React, and why do you need this?" It should be the same question. If you don\'t have any more questions, move on to the next topic. And you will play the role of an unfriendly and demanding interviewer. You have to constantly induce the interviewee to make mistakes. The first is to embarrass the interviewee, and the goal is to find the true value of the interviewee\'s job. Second, it aims to test the interviewee\'s ability and agility to respond to repeated or intended questions. And ask one question for one answer.]'                + 'function_name: [self_introduction] input : ["self-introduction"] rule: [We will provide an input form including a "self-introduction." Read this "self-introduction" and extract the content to generate a question. just ask one question. Don\'t ask too long questions. The question must have a definite purpose. and Just ask one question at a time.'
                + 'function_name: [Evaluation_position] rule: [First, Deep interviews use open-ended questions to encourage the interviewee to provide detailed explanations about their experiences and knowledge. For example, "Can you describe the most challenging technical problem you\'ve faced in the past?". Second, The interviewer presents real-world scenarios to see how the interviewee approaches and solves problems. This type of question assesses the interviewee\'s problem-solving skills and thought process. Third,  In a deep interview, the interviewer goes beyond basic concepts and asks more in-depth technical questions to gauge the interviewee\'s knowledge. Fourth, The interviewer asks specific questions about the interviewee\'s projects to understand their technical contributions, the tools they used, difficulties faced, and achievements. Fifth, the interviewer explores how the interviewer approaches and solves problems to gain deeper insight into their problem-solving skills. Finally, we evaluate technical choices and judgments through technical discussions with interviewees. Using these approaches, actively draw out the interviewee\'s real abilities and competencies during the interview.  Based on this, you ask one question at a time.]'
                + 'interviewee_info(Company="'
                + selector_name
                + '", Job="'
                + job_name
                + '", Career="'
                + career
                + '")'
                + 'self_introduction("'
                + resume
                + '")'
                + "aggressive_position()",
            }
        ]
        
        
    def personal_interview_tuning(self, selector_name, job_name, career, resume):
        self.conversation = [
            {
                "role": "user",
                "content": 'function_name: [personality_interview] input: ["sector", "job", "career", "resume", "number_of_questions"] rule: [I want you to act as a strict interviewer, asking personality questions for the interviewee. I will provide you with input forms including "sector", "job", "career", "resume", and "number_of_questions". I have given inputs, but you do not have to refer to those. Your task is to simply make common personality questions and provide questions to me. You should create total of "number_of_questions" amount of questions, and provide it once at a time. You should ask the next question only after I have answered to the question. Do not include any explanations or additional information in your response, simply provide the generated question. You should also provide only one question at a time. Example questions would be questions such as "How do you handle stress and pressure?", "If you could change one thing about your personality, what would it be and why?". Remember, these questions are related to personality. Once all questions are done, you should just say "수고하셨습니다." You must speak only in Korean during the interview.] personality_interview('
                + str(selector_name)
                + ", "
                + str(job_name)
                + ", "
                + str(career)
                + ", "
                + str(resume)
                + ", 3)",
            }
        ]