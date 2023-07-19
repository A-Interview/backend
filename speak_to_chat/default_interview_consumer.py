from channels.generic.websocket import WebsocketConsumer
import openai
from .models import Form
from dotenv import load_dotenv
import os
import json
from .models import Form, Question, Answer
from asgiref.sync import sync_to_async
from django.core.files.base import ContentFile
import tempfile
import base64

from .tasks import process_whisper_data
from .gpt_answer import add_gptanswer # gpt_answer.py에서 add_gptanswer() 함수 불러옴

load_dotenv()
openai.api_key = os.getenv("GPT_API_KEY")


class DefaultInterviewConsumer(WebsocketConsumer):
    def connect(self):
        self.accept()
        # 대화 기록을 저장할 리스트
        self.conversation = []

    def disconnect(self, close_code):
        pass

    def receive(self, text_data):
        data = json.loads(text_data)

        print(data["formId"])
        print(data["type"])

        # 오디오 파일이 없는 경우
        if data["type"] == "withoutAudio":
            form_object = Form.objects.get(id=data["formId"])

            # 기본 튜닝
            self.default_tuning()

            # 대화 계속하기
            self.continue_conversation(form_object)
        else:
            # base64 디코딩
            audio_blob = data["audioBlob"]
            audio_data = base64.b64decode(audio_blob)

            # 오디오 파일로 변환
            audio_file = ContentFile(audio_data)

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
            last_low = Question.objects.latest("question_id")

            # 답변 테이블에 추가
            Answer.objects.create(content=transcription, question_id=last_low)
            answer_object = Answer.objects.latest("answer_id")
            print(transcription)

            # formId를 통해서 question 테이블을 가져옴
            form_object = Form.objects.get(id=data["formId"])
            questions = form_object.questions.all()

            self.default_tuning()

            # question 테이블에서 질문과 답변에 대해 튜닝 과정에 추가함.
            try:
                for question in questions:
                    answer = question.answer
                    self.add_question_answer(question.content, answer.content)
            except:
                error_message = "같은 지원 양식의 question 테이블과 answer 테이블의 갯수가 일치하지 않습니다."
                print(error_message)
                
            # =========================gpt_answer===============================      
            # 질문, 답변 텍스트 가져오기
            question = last_low.content
            answer = answer_object.content
            
            # gpt 모범 답변 튜닝 및 생성
            gpt_answer = add_gptanswer(question, answer)
            
            # gpt 모범 답변 객체 생성
            gpt_object = GPTAnswer.objects.create(question_id=question_object, content=gpt_answer)
            # =========================gpt_answer===============================

            self.continue_conversation(form_object)

            temp_file.close()

            # 임시 파일 삭제
            os.unlink(temp_file_path)

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
            if chunk.choices[0].finish_reason == "stop":
                break

            message = chunk.choices[0].delta["content"]

            messages += message

            # 메시지를 클라이언트로 바로 전송
            self.send(json.dumps({"message": message}))

        Question.objects.create(content=messages, form_id=form_object)

    # 기본 면접 기본 튜닝
    def default_tuning(self):
            # 대화 시작 메시지 추가
        self.conversation.append(
            {
                "role": "system",
                "content": "You're a interviewer. You don't make any unnecessary expressions asides from giving interview questions.",
            }
        )
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
                        You must speak only in Korean during the interview.] personality_interview("5")'
            }
        )