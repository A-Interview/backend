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
from .tasks import process_whisper_data
import random
import time

from forms.models import Qes_Num

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

            # 이전 면접에서 저장되었던 질문 수
            form_object = Form.objects.get(id=data["formId"])
            questions = form_object.questions.all()
            self.before_qes = questions.count()

            Qes_Num.objects.create(
                total_que_num=self.question_number,
                default_que_num=self.default_question_num,
                situation_que_num=self.situation_question_num,
                deep_que_num=self.deep_question_num,
                personality_que_num=self.personality_question_num,
                form_id=form_object,
            )

        else:
            self.interview_type = data["interviewType"]

            # 기본 면접인 경우
            if self.interview_type == "default":
                print("기본 면접의 경우")

                # 기본 면접 튜닝
                #self.default_interview_tuning()

                # 오디오 파일이 없는 경우
                if data["type"] == "withoutAudio":
                    form_object = Form.objects.get(id=data["formId"])

                    # 대화 계속하기
                    # self.continue_conversation(form_object)
                    
                    # 가장 처음 할 질문
                    first_question = "1분 자기소개를 해주세요."
                    
                    # 최초 기본 면접 질문
                    self.default_conversation(form_object, first_question)

                # 오디오 파일이 있는 경우
                elif data["type"] == "withAudio":

                    # base64 디코딩
                    audio_blob = data["audioBlob"]
                    audio_data = base64.b64decode(audio_blob)

                    # 오디오 파일로 변환
                    audio_file = ContentFile(audio_data)
                    
                    audio_file_url = get_file_url("audio", audio_file)

                    # celery에 temp_file_path 전달해서 get()을 통해 동기적으로 실행(결과가 올 때까지 기다림)
                    transcription = process_whisper_data.delay(audio_file_url).get()

                    # Question 테이블의 마지막 Row 가져오기
                    last_question = Question.objects.latest("question_id")

                    # 답변 테이블에 추가
                    Answer.objects.create(content=transcription, question_id=last_question, recode_file=audio_file_url)
                    print(transcription)

                    # formId를 통해서 question 테이블을 가져옴
                    form_object = Form.objects.get(id=data["formId"])
                    questions = form_object.questions.all().order_by('question_id')

                    # 기존 questions 데이터를 슬라이싱하여 새롭게 생성된 questions만 가져옴
                    questions_included = questions[self.before_qes:]
                    #print(questions_included)

                    for question in questions_included:
                        if question.answer is None:
                            error_message = "같은 지원 양식의 question 테이블과 answer 테이블의 갯수가 일치하지 않습니다."
                            print(error_message)
                    
                    # 랜덤으로 질문 뽑기
                    pick_question = self.pick_random_question()
                    
                    # 뽑은 질문을 client에게 보내기
                    self.default_conversation(form_object, pick_question)

                
                # 대답만 추가하는 경우
                elif data["type"] == "noReply":
                    print("noReply")

                    # base64 디코딩
                    audio_blob = data["audioBlob"]
                    audio_data = base64.b64decode(audio_blob)

                    # 오디오 파일로 변환
                    audio_file = ContentFile(audio_data)

                    # 파일 업로드 및 URL 받아오기
                    audio_file_url = get_file_url("audio", audio_file)

                    # celery에 s3_url 전달해서 get()을 통해 동기적으로 실행(결과가 올 때까지 기다림)
                    transcription = process_whisper_data.delay(audio_file_url).get()
                    print(transcription)

                    # Question 테이블의 마지막 Row 가져오기
                    last_question = Question.objects.latest("question_id")

                    # 답변 테이블에 추가
                    Answer.objects.create(content=transcription, question_id=last_question, recode_file=audio_file_url)
                    self.send(json.dumps({"last_topic_answer":"default_last"}))

                    # 이전 질문 개수에 기본면접 질문 개수 더하여 저장
                    self.before_qes += self.default_question_num

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
                    audio_file_url = get_file_url("audio", audio_file)

                    # celery에 temp_file_path 전달해서 get()을 통해 동기적으로 실행(결과가 올 때까지 기다림)
                    transcription = process_whisper_data.delay(audio_file_url).get()

                    # Question 테이블의 마지막 Row 가져오기
                    last_question = Question.objects.latest("question_id")

                    # 답변 테이블에 추가
                    Answer.objects.create(
                        content=transcription, question_id=last_question, recode_file=audio_file_url
                    )
                    print(transcription)

                    # formId를 통해서 question 테이블을 가져옴
                    form_object = Form.objects.get(id=data["formId"])
                    questions = form_object.questions.all().order_by('question_id')

                    # 기존 questions 데이터를 슬라이싱하여 새롭게 생성된 questions만 가져옴
                    questions_included = questions[self.before_qes:]
                    # print(questions_included)

                    self.situation_interview_tuning(
                        form_object.sector_name,
                        form_object.job_name,
                        form_object.career,
                    )

                    # question 테이블에서 질문과 답변에 대해 튜닝 과정에 추가함.
                    try:
                        for question in questions_included:
                            answer = question.answer
                            self.add_question_answer(question.content, answer.content)
                    except:
                        error_message = "같은 지원 양식의 question 테이블과 answer 테이블의 갯수가 일치하지 않습니다."
                        print(error_message)

                    self.continue_conversation(form_object)

                    
                elif data["type"] == "noReply":
                    # base64 디코딩
                    audio_blob = data["audioBlob"]
                    audio_data = base64.b64decode(audio_blob)

                    # 오디오 파일로 변환
                    audio_file = ContentFile(audio_data)

                    # 파일 업로드 및 URL 받아오기
                    audio_file_url = get_file_url("audio", audio_file)

                    # celery에 temp_file_path 전달해서 get()을 통해 동기적으로 실행(결과가 올 때까지 기다림)
                    transcription = process_whisper_data.delay(audio_file_url).get()

                    # Question 테이블의 마지막 Row 가져오기
                    last_question = Question.objects.latest("question_id")

                    # 답변 테이블에 추가
                    Answer.objects.create(
                        content=transcription, question_id=last_question, recode_file=audio_file_url
                    )
                    self.send(json.dumps({"last_topic_answer":"situation_last"}))

                    # 이전 질문 개수에 상황면접 질문 개수 누적
                    self.before_qes += self.situation_question_num

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
                    audio_file_url=get_file_url("audio", audio_file)

                    # celery에 temp_file_path 전달해서 get()을 통해 동기적으로 실행(결과가 올 때까지 기다림)
                    transcription = process_whisper_data.delay(audio_file_url).get()

                    # Question 테이블의 마지막 Row 가져오기
                    last_question = Question.objects.latest("question_id")

                    # 답변 테이블에 추가
                    Answer.objects.create(content=transcription, question_id=last_question, recode_file=audio_file_url)
                    print(transcription)

                    # formId를 통해서 question 테이블을 가져옴
                    form_object = Form.objects.get(id=data["formId"])
                    questions = form_object.questions.all().order_by('question_id')

                    # 기존 questions 데이터를 슬라이싱하여 새롭게 생성된 questions만 가져옴
                    questions_included = questions[self.before_qes:]
                    # print(questions_included)

                    self.deep_interview_tuning(
                        form_object.sector_name,
                        form_object.job_name,
                        form_object.career,
                        form_object.resume,
                    )

                    # question 테이블에서 질문과 답변에 대해 튜닝 과정에 추가함.
                    try:
                        for question in questions_included:
                            answer = question.answer
                            self.add_question_answer(question.content, answer.content)
                    except:
                        error_message = "같은 지원 양식의 question 테이블과 answer 테이블의 갯수가 일치하지 않습니다."
                        print(error_message)

                    self.continue_conversation(form_object)


                # 대답만 추가하는 경우
                elif data["type"] == "noReply":
                    # base64 디코딩
                    audio_blob = data["audioBlob"]
                    audio_data = base64.b64decode(audio_blob)

                    # 오디오 파일로 변환
                    audio_file = ContentFile(audio_data)

                    # 파일 업로드 및 URL 받아오기
                    audio_file_url = get_file_url("audio", audio_file)

                    # celery에 s3_url 전달해서 get()을 통해 동기적으로 실행(결과가 올 때까지 기다림)
                    transcription = process_whisper_data.delay(audio_file_url).get()

                    # Question 테이블의 마지막 Row 가져오기
                    last_question = Question.objects.latest("question_id")

                    # 답변 테이블에 추가
                    Answer.objects.create(content=transcription, question_id=last_question, recode_file=audio_file_url)
                    self.send(json.dumps({"last_topic_answer":"deep_last"}))

                    # 이전 질문 개수에 심층면접 질문 개수 누적
                    self.before_qes += self.deep_question_num

            else:
                pass 

            # 성향 면접인 경우
            if self.interview_type == "personality":
                print("성향 면접의 경우")
                # 오디오 파일이 없는 경우
                if data["type"] == "withoutAudio":
                    form_object = Form.objects.get(id=data["formId"])

                    # 기본 튜닝
                    self.personal_interview_tuning()

                    # 대화 계속하기
                    self.continue_conversation(form_object)
                    
                elif data["type"] == "withAudio":
                    # base64 디코딩
                    audio_blob = data["audioBlob"]
                    audio_data = base64.b64decode(audio_blob)

                    # 오디오 파일로 변환
                    audio_file = ContentFile(audio_data)

                    # 파일 업로드 및 URL 받아오기
                    audio_file_url = get_file_url("audio", audio_file)

                    # celery에 temp_file_path 전달해서 get()을 통해 동기적으로 실행(결과가 올 때까지 기다림)
                    transcription = process_whisper_data.delay(audio_file_url).get()

                    # Question 테이블의 마지막 Row 가져오기
                    last_question = Question.objects.latest("question_id")

                    # 답변 테이블에 추가
                    Answer.objects.create(
                        content=transcription, question_id=last_question, recode_file=audio_file_url
                    )
                    print(transcription)

                    # formId를 통해서 question 테이블을 가져옴
                    form_object = Form.objects.get(id=data["formId"])
                    questions = form_object.questions.all().order_by('question_id')

                    # 기존 questions 데이터를 슬라이싱하여 새롭게 생성된 questions만 가져옴
                    questions_included = questions[self.before_qes:]
                    # print(questions_included)

                    self.personal_interview_tuning()

                    # question 테이블에서 질문과 답변에 대해 튜닝 과정에 추가함.
                    try:
                        for question in questions_included:
                            answer = question.answer
                            self.add_question_answer(question.content, answer.content)
                    except:
                        error_message = "같은 지원 양식의 question 테이블과 answer 테이블의 갯수가 일치하지 않습니다."
                        print(error_message)

                    self.continue_conversation(form_object)

                # 대답만 추가하는 경우
                elif data["type"] == "noReply":
                    # base64 디코딩
                    audio_blob = data["audioBlob"]
                    audio_data = base64.b64decode(audio_blob)

                    # 오디오 파일로 변환
                    audio_file = ContentFile(audio_data)

                    # 파일 업로드 및 URL 받아오기
                    audio_file_url = get_file_url("audio", audio_file)

                    # celery에 temp_file_path 전달해서 get()을 통해 동기적으로 실행(결과가 올 때까지 기다림)
                    transcription = process_whisper_data.delay(audio_file_url).get()

                    # Question 테이블의 마지막 Row 가져오기
                    last_question = Question.objects.latest("question_id")

                    # 답변 테이블에 추가
                    Answer.objects.create(
                        content=transcription, question_id=last_question, recode_file=audio_file_url
                    )
                    self.send(json.dumps({"last_topic_answer":"personal_last"}))

                    # 이전 질문 개수에 성향면접 질문 개수 누적
                    self.before_qes += self.personality_question_num
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
        self.conversation.append(
            {
                "role": "assistant",
                "content": question
            }
        )
        self.conversation.append(
            {
                "role": "user",
                "content": answer
            }
        )

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
    
    # 기본 면접 한글자 단위로 보내기
    def default_conversation(self, form_object, question_content):
        messages = ""
        # question_content의 index와 원소를 순차적으로 반환하여 스트림 형식으로 출력
        for index, chunk in enumerate(question_content):
            is_last_char = ""
            # 현재 글자가 마지막 글자인지 확인
            if index == len(question_content) - 1:
                is_last_char = "stop"
            else:
                is_last_char = "incomplete"
                
            if is_last_char == "stop" :
                self.send(json.dumps({"message": chunk, "finish_reason": is_last_char}))
                break
            
            message = chunk
            messages += message

            # 메시지를 클라이언트로 바로 전송
            self.send(json.dumps({"message": message, "finish_reason": is_last_char}))
            
            time.sleep(0.05)

        Question.objects.create(content=messages, form_id=form_object)


    # 질문을 랜덤으로 뽑는 함수
    def pick_random_question(self):
        # 중복 질문이 나오면 다시 뽑음 (그냥 삭제하는 걸로 할까?)
        pick_question = []
        while True:
            basic_questions_list = [
                "우리 회사에 지원한 동기가 무엇입니까?",
                "자신의 장점과 단점에 대해 이야기해보세요.",
                "최근에 읽은 책이나 영화는 무엇입니까?",
                "본인의 취미나 특기가 무엇입니까?",
                "자신만에 스트레스 해소법은 무엇입니까?",
                "5년 뒤, 10년 뒤 자신의 모습이 어떨 것 같습니까?",
                "가장 존경하는 인물은 누구입니까?",
                "본인이 추구하는 가치나 생활신조, 인생관, 좌우명은 무엇입니까?",
                "자기 계발을 위해 무엇을 합니까?",
                "취업기간에 무엇을 하셨나요?",
                "가장 기억에 남는 갈등 경험을 말해주세요",
                "가장 필요한 역량은 무엇이라 생각하나요?",
                "우리 회사의 단점이 무엇이라고 생각하나요?",
                "성취를 이룬 경험이 있나요? 그 경험을 설명해주세요.",
                "과거에 어떤 도전적인 상황을 겪었으며, 그 상황에서 어떻게 대응했나요?",
                ]

            question = random.choice(basic_questions_list)

            if question in pick_question:
                continue
            pick_question.append(question)
            break

        return question
        
    # 상황 면접 튜닝
    def situation_interview_tuning(self, selector_name, job_name, career):
        self.conversation = []
        self.conversation.append(
            {
                "role": "system",
                "content": 'function_name: [situation_interview] rule: [Act as an interviewer for a company. For example, if the question asks, "What would you do if your boss gives an unfair work order?" the answer is, "I refuse because I can\'t do anything unfair." Ask questions about the applicant\'s ability to cope with the situation]'
                + "function_name: [default] rule: [You should provide only one question at a time. You should not ask questions that have been asked before. You must speak only in Korean during the interview.]"
                + 'function_name: [onlyAnswer] rule: [Don\'t say anything other than a question]'
            }
        )
        self.conversation.append(
            {
                "role": "assistant",
                "content" : "All users are unable to connect due to a sudden problem with the database of the web application being used by the company. What steps will you follow to resolve this issue?"
            }
        )
        self.conversation.append(
            {
                "role": "user",
                "content": "First, check log files and server monitoring to determine the cause of the error. Next, verify that the database server is operating correctly, and restart or restart the database service if there are any problems. If this doesn't solve the problem, check your backend code and queries to fix and optimize bad queries or inefficient code. And if the problem is system-wide, it checks for server resource shortages and takes the necessary action."
            },
        )
        self.conversation.append(
            {
                "role": "assistant",
                "content": "You want to add a new index to the database server. Anticipate how this will affect the performance of your web application, and what to consider when adding indexes?"
            },
        )
        self.conversation.append(
            {
                "role": "user",
                "content": "Adding indexes is expected to improve database lookup performance. This can improve performance, especially for queries that retrieve large amounts of data. However, indexes can incur performance penalties when inserting, modifying, or deleting data, so you need to take this into account. When adding indexes, choose frequently used search fields and be careful not to create duplicate indexes. Additionally, it is important to keep database statistics updated to maintain optimal execution plans."
            }
        )
        self.conversation.append(
            {
                "role": "assistant",
                "content": "For added security, we want to store the user's password using a one-way hash function. Which hash function to choose and what to consider when applying a hash function?"
            }
        )
        self.conversation.append(
            {
                "role": "user",
                "content": "Session and token-based authentication methods each have their pros and cons, so you should choose one that suits your situation. Session-based authentication uses more resources on the server side as it maintains state on the server. On the other hand, token-based authentication maintains state on the client, which can reduce server load. Also, tokens are often JSON Web Tokens (JWTs), which provide signed tokens that cannot be changed on the client. However, the token must be managed securely, and the expiration time and renewal method must be carefully set."
            }
        )
        self.conversation.append(
            {
                "role": "system",
                "content": "situation_interview(Company="
                + selector_name
                + ", Job="
                + job_name
                + ", Career="
                + career
                + ")"
                + "default()"
                + "onlyAnswer()"
            }
        )
    
    # 심층 면접 튜닝 
    def deep_interview_tuning(self, selector_name, job_name, career, resume):
        self.conversation = [
            {
                "role": "system",
                "content": 'Resume: ' 
                + str(resume)
            },
            {
                "role": "system",
                "content": 'function_name: [deep_interview], Company: ' 
                + str(selector_name) 
                + ', Job: ' 
                + str(job_name) 
                + ', Career: ' 
                + str(career) 
                + ', Rule: [ You play the role of a strict and skillful interviewer for the company. For example, if the question asks, "What was the most difficult project or task at your previous job?" the answer is, "The most challenging task was planning and executing a marketing strategy for a product launch." The interviewer can then ask follow-up questions based on this answer. "What was the biggest challenge in that project? How did you overcome it?" or  "What was your role in that project? What results did you achieve?" Pressure applicants and evaluate their thinking skills, problem-solving skills, communication skills, honesty and integrity, reflection and learning skills.]'
            },
            {
                "role": "system",
                "content": "function_name: [default], Rule: [You should provide only one question at a time. You should not ask questions that have been asked before. You must speak only in Korean during the interview.]"
            },
            {
                "role": "system",
                "content": 'function_name: [onlyAnswer], Rule: [Don\'t say anything other than a question. You must speak only in Korean during the interview. Don\'t ask duplicate questions. Don\'t ask questions about the examples I\'ve presented, just refer to them.]'
            },
            {"role": "assistant", "content": "Can you tell me about a challenging project you've worked on in the past based on your resume?"},
            {"role": "user", "content": "Sure, I worked on a data migration project at my previous job. It was quite challenging."},
            {"role": "assistant", "content": "That sounds interesting. What made this data migration project particularly challenging?"},
            {"role": "user", "content": "The project required us to migrate a large amount of data from an old system to a new one, and there were a lot of technical difficulties."},
            {"role": "assistant to=deep_interview", "content": "I see. Can you describe some of the technical difficulties and how you addressed them?"}
        ]


    def personal_interview_tuning(self):
        self.conversation = [
            {
                "role": "system",
                "content": "You are a strict interviewer. You will ask the user personality interview questions commonly asked in job interviews. You shouldn't make any unnecessary expressions aside from asking questions."
            },

            {
                "role": "user",
                "content": 'I want you to give personality questions for the interviewee. Your task is to simply ask common personality questions that interviewers ask in job interviews. You should only focus on providing questions, and not say any unnecessary expressions. Provide only one question at a time. Do not ever to not include any explanations or additional information in your response. Simply provide the generated question please. Remember to only provide questions that are related to personality. You must speak only in Korean during the interview. Keep in mind - Don\'t ask the interviewee to introduce himself. Don\'t even greet the interviewee. Just ask interview questions, one at a time.'
            }
        ]
