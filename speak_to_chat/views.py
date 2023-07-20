from django.shortcuts import render
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import generics
from drf_yasg.utils import swagger_auto_schema
from dotenv import load_dotenv
import openai
import base64
from .tasks import process_whisper_data
from django.core.files.base import ContentFile
from .models import Answer, Question, GPTAnswer
import os
from .serializers import ResponseVoiceSerializer
from django.core.files.temp import NamedTemporaryFile
from rest_framework.parsers import MultiPartParser
from rest_framework.decorators import action
from drf_yasg import openapi
from django.shortcuts import get_object_or_404
from forms.models import Form
from .models import Question
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
import random
from django.http import HttpResponse
from django.http import JsonResponse

from .tasks import process_whisper_data
from .gpt_answer import add_gptanswer

load_dotenv()
openai.api_key = os.getenv("GPT_API_KEY")


# 기본 인터뷰
class DefaultInterview(APIView):
    parser_classes = [MultiPartParser]
    conversation = []

    # 답변과 상관없이 질문을 랜덤으로 뽑아서 지원자에게 질문
    @swagger_auto_schema(
        operation_description="심층 면접 데이터 최초 받기",
        operation_id="form_id를 입력해주세요.",
        manual_parameters=[
            openapi.Parameter(
                name="form_id",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="form_id",
            )
        ],
        responses={"200": ResponseVoiceSerializer},
    )
    def get(self, request):
        # 최초의 질문은 자기소개로 고정
        message = "1분 자기소개를 해주세요."

        # form_id 받기, 파라미터로 받기
        # request.GET.get 이해 못함. 공부할 것것
        # GET :
        # get() :
        form_id = request.GET.get("form_id")

        # form_id에 해당하는 Form 객체 생성
        form_object = Form.objects.get(id=form_id)

        # Question 테이블에 Form 객체 데이터 추가
        # form_id=form_object : Question의 외래키를 추가하여 연결시킴
        Question.objects.create(content=message, form_id=form_object)

        return Response(message, status=status.HTTP_200_OK)

    # 음성 데이터를 받아야 하는 경우
    @swagger_auto_schema(
        # API 작업에 대한 설명
        operation_description="음성 데이터 POST",
        # 작업의 고유 식별자
        operation_id="음성 파일을 업로드 해주세요.",
        # voice_file 파일을 업로드하는 매개변수를 정의
        manual_parameters=[
            openapi.Parameter(
                name="form_id",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="지원 정보 아이디",
            ),
            openapi.Parameter(
                name="question_id",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="질문 아이디",
            ),
            openapi.Parameter(
                name="voice_file",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_FILE,
                required=True,
                description="음성 데이터",
            ),
        ],
        # API 응답에 대한 설명
        responses={400: "Invalid data in uploaded file", 200: "Success"},
    )
    # @action : Django ViewSet에서 사용되며, 특정 작업에 대한 추가적인 액션을 정의할 때 사용
    @action(
        detail=False,
        methods=["post"],
        parser_classes=(MultiPartParser,),
        name="upload-voice-file",
        url_path="upload-voice-file",
    )
    def post(self, request, format=None):

        # # 음성 답변 받기
        # audio_file = request.FILES["voice_file"]
        form_id = request.data["form_id"]
        question_id = request.data["question_id"]
        # # 음성 -> 텍스트
        # transcript = openai.Audio.transcribe("whisper-1", audio_file)
        # transcription = transcript["text"]

        # delay() : celery 작업 즉, 비동기적으로 작업 예
		# delay() 함수를 통해 tasks.py의 process_whisper_data를 실행
        transcription = process_whisper_data.delay()

        # 답변 테이블에 추가
        question_object = Question.objects.get(question_id=question_id)
        Answer.objects.create(content=transcription, question_id=question_object)
        answer_object = Answer.objects.get(question_id=question_id)

        # id=form_id인 Form 객체 가져오기(get)
        form_info = Form.objects.get(id=form_id)
        questions = form_info.questions.all()
        
        # 기본 튜닝
        self.default_tuning()
        
        try:
            # 질문, 대답 추가.
            for question in questions:
                answer = question.answer
                self.add_question_answer(question.content, answer.content)
        except:
            error_message = "같은 지원 양식의 question 테이블과 answer 테이블의 갯수가 일치하지 않습니다."
            response = HttpResponse(error_message, status=500)
            return response
            
        
        
        # =========================gpt_answer===============================      
        # 질문, 답변 텍스트 가져오기
        question = question_object.content
        answer = answer_object.content
        
        # gpt 모범 답변 튜닝 및 생성
        # gpt_answer = self.add_gptanswer(question, answer)
        gpt_answer = add_gptanswer(question, answer)
        
        
        # gpt 모범 답변 객체 생성
        gpt_object = GPTAnswer.objects.create(question_id=question_object, content=gpt_answer)
        # =========================gpt_answer===============================
        
        # gpt에게 답변 & 새로운 질문 받기
        message = self.continue_conversation()
        
        # 새로운 질문 추가
        Question.objects.create(content=message, form_id=form_info)
        
        QnA = {
            "QnA": {
                "Answer": answer,
                "GPT_Answer": gpt_answer,
                "다음 질문": message
            }
        }

        # Response객체를 생성하여 데이터와 상태 코드 반환
        return Response(QnA, status=status.HTTP_200_OK)
    
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
    
    # 질문과 대답 추가
    def add_question_answer(self, question, answer):
        self.conversation.append({"role": "assistant", "content": question})
        self.conversation.append({"role": "assistant", "content": answer})

    def continue_conversation(self):
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", messages=self.conversation, temperature=0.9, n=1
        )

        message = completion.choices[0].message["content"]
        return message

# 상황 부여 면접
class SituationInterview(APIView):
    conversation = []
    # 처음 데이터를 받아야 하는 경우 -> 음성 데이터는 없음. 그냥 GPT 질문 시작.
    @swagger_auto_schema(
        operation_description="상황 면접 데이터 최초 받기",
        operation_id="form_id를 입력해주세요.",
        manual_parameters=[
            openapi.Parameter(
                name="form_id",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="form_id",
            )
        ],
        responses={"200": ResponseVoiceSerializer},
    )

    def get(self, request):
        form_id = request.GET.get("form_id")
        # Question 테이블에 데이터 추가, form Object 얻기
        form_object = Form.objects.get(id=form_id)

        # 기본 튜닝
        self.default_tuning(
            form_object.sector_name,
            form_object.job_name,
            form_object.career,
        )

        # 대화 계속하기
        message = self.continue_conversation()

        Question.objects.create(content=message, form_id=form_object)

        return Response(message, status=status.HTTP_200_OK)

    # 음성 데이터를 받아야 하는 경우

    @swagger_auto_schema(
        operation_description="음성 데이터 POST",
        operation_id="음성 파일을 업로드 해주세요.",
        manual_parameters=[
            openapi.Parameter(
                name="form_id",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="지원 정보 아이디",
            ),
            openapi.Parameter(
                name="question_id",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="질문 아이디",
            ),
            openapi.Parameter(
                name="voice_file",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_FILE,
                required=True,
                description="음성 데이터",
            ),
        ],
        responses={400: "Invalid data in uploaded file", 200: "Success"},
    )
    @action(
        detail=False,
        methods=["post"],
        parser_classes=(MultiPartParser,),
        name="upload-voice-file",
        url_path="upload-voice-file",
    )
    def post(self, request, format=None):
        # 답변을 받고, 응답을 해주는 부분 -> 음성 파일 추출 필요
        # 오디오 파일, 지원 정보 아이디, 질문 아이디를 Request Body로 받음
        self.conversation = []
        # audio_file = request.FILES["voice_file"]
        # form_id = request.data["form_id"]
        # question_id = request.data["question_id"]
        # transcript = openai.Audio.transcribe("whisper-1", audio_file)
        # transcription = transcript["text"]

        # S3에 업로드하는 로직 필요!
        
        # delay() : celery 작업 즉, 비동기적으로 작업 예
		# delay() 함수를 통해 tasks.py의 process_whisper_data를 실행
        transcription = process_whisper_data.delay()

        # 답변 테이블에 추가
        question_object = Question.objects.get(question_id=question_id)
        Answer.objects.create(content=transcription, question_id=question_object)

        form_object = Form.objects.get(id=form_id)
        questions = form_object.questions.all()

        # 기본 튜닝
        self.default_tuning(
            form_object.sector_name,
            form_object.job_name,
            form_object.career,
        )

        try:
            # 질문, 대답 추가.
            for question in questions:
                answer = question.answer
                self.add_question_answer(question.content, answer.content)
        except:
            error_message = "같은 지원 양식의 question 테이블과 answer 테이블의 갯수가 일치하지 않습니다."
            response = HttpResponse(error_message, status=500)
            return response
        
        # =========================gpt_answer===============================      
        # 질문, 답변 텍스트 가져오기
        question = question_object.content
        answer = answer_object.content
        
        # gpt 모범 답변 튜닝 및 생성
        # gpt_answer = self.add_gptanswer(question, answer)
        gpt_answer = add_gptanswer(question, answer)
        
        # gpt 모범 답변 객체 생성
        gpt_object = GPTAnswer.objects.create(question_id=question_object, content=gpt_answer)
        # =========================gpt_answer===============================

        message = self.continue_conversation()

        # 질문 테이블에 정보 추가
        Question.objects.create(content=message, form_id=form_object)

        return Response(message, status=status.HTTP_200_OK)

    # 질문과 대답 추가
    def add_question_answer(self, question, answer):
        self.conversation.append({"role": "assistant", "content": question})
        self.conversation.append({"role": "assistant", "content": answer})

    def continue_conversation(self):
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", messages=self.conversation, temperature=0.9, n=1
        )

        message = completion.choices[0].message["content"]
        return message

    # 기본 튜닝
    def default_tuning(self, seletor_name, job_name, career):
        # 대화 시작 메시지 추가
        self.conversation.append(
            {
                "role": "user",
                "contenet": 'function_name: [situation_interview] input: ["sector", "job", "career"] rule: [You are an expert in recruitment and interviewer specializing in finding the best talent. Ask questions that can judge my ability to cope with situations based “job” that I’ll provide and ask once at a time. For example, you would be ask such as "You have been assigned to work on a project where the design team has provided you with a visually appealing but intricate UI design for a web page. As you start implementing it, you realize that some of the design elements may not be feasible to achieve with the current technology or may negatively impact the performance. How would you handle this situation?" You should ask the next question only after I have answered to the question. Never ask a question similar to the previous one include example that i provide. Do not include any explanations or additional information in your response, simply provide a question in korean. Do not say anything other than a question.]'
                + "situation_interview(Company="
                + seletor_name
                + ", Job="
                + job_name
                + ", Career="
                + career
                + ")"
            }
        )

# 상황 부여 면접
class SituationInterview(APIView):
    conversation = []
    # 처음 데이터를 받아야 하는 경우 -> 음성 데이터는 없음. 그냥 GPT 질문 시작.
    @swagger_auto_schema(
        operation_description="상황 면접 데이터 최초 받기",
        operation_id="form_id를 입력해주세요.",
        manual_parameters=[
            openapi.Parameter(
                name="form_id",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="form_id",
            )
        ],
        responses={"200": ResponseVoiceSerializer},
    )

    def get(self, request):
        form_id = request.GET.get("form_id")
        # Question 테이블에 데이터 추가, form Object 얻기
        form_object = Form.objects.get(id=form_id)

        # 기본 튜닝
        self.default_tuning(
            form_object.sector_name,
            form_object.job_name,
            form_object.career,
        )

        # 대화 계속하기
        message = self.continue_conversation()

        Question.objects.create(content=message, form_id=form_object)

        return Response(message, status=status.HTTP_200_OK)

    # 음성 데이터를 받아야 하는 경우

    @swagger_auto_schema(
        operation_description="음성 데이터 POST",
        operation_id="음성 파일을 업로드 해주세요.",
        manual_parameters=[
            openapi.Parameter(
                name="form_id",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="지원 정보 아이디",
            ),
            openapi.Parameter(
                name="question_id",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="질문 아이디",
            ),
            openapi.Parameter(
                name="voice_file",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_FILE,
                required=True,
                description="음성 데이터",
            ),
        ],
        responses={400: "Invalid data in uploaded file", 200: "Success"},
    )
    @action(
        detail=False,
        methods=["post"],
        parser_classes=(MultiPartParser,),
        name="upload-voice-file",
        url_path="upload-voice-file",
    )
    def post(self, request, format=None):
        # 답변을 받고, 응답을 해주는 부분 -> 음성 파일 추출 필요
        # 오디오 파일, 지원 정보 아이디, 질문 아이디를 Request Body로 받음
        self.conversation = []
        # audio_file = request.FILES["voice_file"]
        # form_id = request.data["form_id"]
        # question_id = request.data["question_id"]
        # transcript = openai.Audio.transcribe("whisper-1", audio_file)
        # transcription = transcript["text"]

        # S3에 업로드하는 로직 필요!
        
        # delay() : celery 작업 즉, 비동기적으로 작업 예
		# delay() 함수를 통해 tasks.py의 process_whisper_data를 실행
        transcription = process_whisper_data.delay()

        # 답변 테이블에 추가
        question_object = Question.objects.get(question_id=question_id)
        Answer.objects.create(content=transcription, question_id=question_object)

        form_object = Form.objects.get(id=form_id)
        questions = form_object.questions.all()

        # 기본 튜닝
        self.default_tuning(
            form_object.sector_name,
            form_object.job_name,
            form_object.career,
        )

        try:
            # 질문, 대답 추가.
            for question in questions:
                answer = question.answer
                self.add_question_answer(question.content, answer.content)
        except:
            error_message = "같은 지원 양식의 question 테이블과 answer 테이블의 갯수가 일치하지 않습니다."
            response = HttpResponse(error_message, status=500)
            return response
        
        # =========================gpt_answer===============================      
        # 질문, 답변 텍스트 가져오기
        question = question_object.content
        answer = answer_object.content
        
        # gpt 모범 답변 튜닝 및 생성
        # gpt_answer = self.add_gptanswer(question, answer)
        gpt_answer = add_gptanswer(question, answer)
        
        # gpt 모범 답변 객체 생성
        gpt_object = GPTAnswer.objects.create(question_id=question_object, content=gpt_answer)
        # =========================gpt_answer===============================

        message = self.continue_conversation()

        # 질문 테이블에 정보 추가
        Question.objects.create(content=message, form_id=form_object)

        return Response(message, status=status.HTTP_200_OK)

    # 질문과 대답 추가
    def add_question_answer(self, question, answer):
        self.conversation.append({"role": "assistant", "content": question})
        self.conversation.append({"role": "assistant", "content": answer})

    def continue_conversation(self):
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", messages=self.conversation, temperature=0.9, n=1
        )

        message = completion.choices[0].message["content"]
        return message

    # 기본 튜닝
    def default_tuning(self, seletor_name, job_name, career):
        # 대화 시작 메시지 추가
        self.conversation.append(
            {
                "role": "user",
                "contenet": 'function_name: [situation_interview] input: ["sector", "job", "career"] rule: [You are an expert in recruitment and interviewer specializing in finding the best talent. Ask questions that can judge my ability to cope with situations based “job” that I’ll provide and ask once at a time. For example, you would be ask such as "You have been assigned to work on a project where the design team has provided you with a visually appealing but intricate UI design for a web page. As you start implementing it, you realize that some of the design elements may not be feasible to achieve with the current technology or may negatively impact the performance. How would you handle this situation?" You should ask the next question only after I have answered to the question. Never ask a question similar to the previous one include example that i provide. Do not include any explanations or additional information in your response, simply provide a question in korean. Do not say anything other than a question.]'
                + "situation_interview(Company="
                + seletor_name
                + ", Job="
                + job_name
                + ", Career="
                + career
                + ")"
            }
        )


# 심층 면접 인터뷰
class DeepInterview(APIView):
    conversation = []

    # 처음 데이터를 받아야 하는 경우 -> 음성 데이터는 없음. 그냥 GPT 질문 시작.
    @swagger_auto_schema(
        operation_description="심층 면접 데이터 최초 받기",
        operation_id="form_id를 입력해주세요.",
        manual_parameters=[
            openapi.Parameter(
                name="form_id",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="form_id",
            )
        ],
        responses={"200": ResponseVoiceSerializer},
    )
    def get(self, request):
        form_id = request.GET.get("form_id")
        # Question 테이블에 데이터 추가, form Object 얻기
        form_object = Form.objects.get(id=form_id)

        # 기본 튜닝
        self.default_tuning(
            form_object.sector_name,
            form_object.job_name,
            form_object.career,
            form_object.resume,
        )

        # 대화 계속하기
        message = self.continue_conversation()

        Question.objects.create(content=message, form_id=form_object)

        return Response(message, status=status.HTTP_200_OK)

    # 음성 데이터를 받아야 하는 경우

    @swagger_auto_schema(
        operation_description="음성 데이터 POST",
        operation_id="음성 파일을 업로드 해주세요.",
        manual_parameters=[
            openapi.Parameter(
                name="form_id",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="지원 정보 아이디",
            ),
            openapi.Parameter(
                name="question_id",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="질문 아이디",
            ),
            openapi.Parameter(
                name="voice_file",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_FILE,
                required=True,
                description="음성 데이터",
            ),
        ],
        responses={400: "Invalid data in uploaded file", 200: "Success"},
    )
    @action(
        detail=False,
        methods=["post"],
        parser_classes=(MultiPartParser,),
        name="upload-voice-file",
        url_path="upload-voice-file",
    )
    def post(self, request, format=None):
        # 답변을 받고, 응답을 해주는 부분 -> 음성 파일 추출 필요
        # 오디오 파일, 지원 정보 아이디, 질문 아이디를 Request Body로 받음
        self.conversation = []
        # audio_file = request.FILES["voice_file"]
        # form_id = request.data["form_id"]
        # question_id = request.data["question_id"]
        # transcript = openai.Audio.transcribe("whisper-1", audio_file)
        # transcription = transcript["text"]

        # S3에 업로드하는 로직 필요!
        
        # delay() : celery 작업 즉, 비동기적으로 작업 예
		# delay() 함수를 통해 tasks.py의 process_whisper_data를 실행
        transcription = process_whisper_data.delay()

        # 답변 테이블에 추가
        question_object = Question.objects.get(question_id=question_id)
        Answer.objects.create(content=transcription, question_id=question_object)

        form_object = Form.objects.get(id=form_id)
        questions = form_object.questions.all()

        # 기본 튜닝
        self.default_tuning(
            form_object.sector_name,
            form_object.job_name,
            form_object.career,
            form_object.resume,
        )

        try:
            # 질문, 대답 추가.
            for question in questions:
                answer = question.answer
                self.add_question_answer(question.content, answer.content)
        except:
            error_message = "같은 지원 양식의 question 테이블과 answer 테이블의 갯수가 일치하지 않습니다."
            response = HttpResponse(error_message, status=500)
            return response
        
        # =========================gpt_answer===============================      
        # 질문, 답변 텍스트 가져오기
        question = question_object.content
        answer = answer_object.content
        
        # gpt 모범 답변 튜닝 및 생성
        # gpt_answer = self.add_gptanswer(question, answer)
        gpt_answer = add_gptanswer(question, answer)
        
        # gpt 모범 답변 객체 생성
        gpt_object = GPTAnswer.objects.create(question_id=question_object, content=gpt_answer)
        # =========================gpt_answer===============================

        message = self.continue_conversation()

        # 질문 테이블에 정보 추가
        Question.objects.create(content=message, form_id=form_object)

        return Response(message, status=status.HTTP_200_OK)

    # 질문과 대답 추가
    def add_question_answer(self, question, answer):
        self.conversation.append({"role": "assistant", "content": question})
        self.conversation.append({"role": "assistant", "content": answer})

    def continue_conversation(self):
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", messages=self.conversation, temperature=0.9, n=1
        )

        message = completion.choices[0].message["content"]
        return message

    # 기본 튜닝
    def default_tuning(self, seletor_name, job_name, career, resume):
        # 대화 시작 메시지 추가
        self.conversation.append(
            {
                "role": "user",
                "content": 'function_name: [interviewee_info] input: ["Company", "Job", "Career"] rule: [Please act as a skillful interviewer. We will provide the input form including "Company," "Professional," and "Career." Look at the sentences "Company," "Job," and "Career" to get information about me as an interviewee. For example, let\'s say company = IT company, job = web front-end developer, experience = newcomer. Then you can recognize that you\'re a newbie applying to an IT company as a web front-end developer. And you can ask questions that fit this information. You must speak only in Korean during the interview. and you don\'t have to answer.] function_name: [aggresive_position] rule: [Ask me questions in a tail-to-tail manner about what I answer. There may be technical questions about the answer, and there may be questions that you, as an interviewer, would dig into the answer.. For example, if the question asks, "What\'s your web framework?" the answer is, "React." So the new question is, "What do you use as a health management tool in React, and why do you need this?" It should be the same question. If you don\'t have any more questions, move on to the next topic.] function_name: [self_introduction] input : ["self-introduction"] rule: [We will provide an input form including a "self-introduction." Read this "self-introduction" and extract the content to generate a question. just ask one question.]'
                + "interviewee_info(Company="
                + seletor_name
                + ", Job="
                + job_name
                + ", Career="
                + career
                + ")"
                + "self_introduction("
                + resume
                + ")"
                + "agressive_position()",
            }
        )


# 성향(인성) 면접 인터뷰
class PersonalityInterview(APIView):
    conversation = []

    # 처음 데이터를 받아야 하는 경우 -> 음성 데이터는 없음. 그냥 GPT 질문 시작.
    @swagger_auto_schema(
        operation_description="심층 면접 데이터 최초 받기",
        operation_id="form_id를 입력해주세요.",
        manual_parameters=[
            openapi.Parameter(
                name="form_id",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="form_id",
            )
        ],
        responses={"200": ResponseVoiceSerializer},
    )
    def get(self, request):
        # 기본 튜닝
        self.default_tuning()

        # 대화 계속하기
        message = self.continue_conversation()

        # form_id 받기, 파라미터로 받기
        form_id = request.GET.get("form_id")

        # Question 테이블에 데이터 추가, form Object 얻기
        form_object = Form.objects.get(id=form_id)

        Question.objects.create(content=message, form_id=form_object)

        return Response(message, status=status.HTTP_200_OK)

        # 음성 데이터를 받아야 하는 경우

    @swagger_auto_schema(
        operation_description="음성 데이터 POST",
        operation_id="음성 파일을 업로드 해주세요.",
        manual_parameters=[
            openapi.Parameter(
                name="form_id",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="지원 정보 아이디",
            ),
            openapi.Parameter(
                name="question_id",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="질문 아이디",
            ),
            openapi.Parameter(
                name="voice_file",
                in_=openapi.IN_FORM,
                type=openapi.TYPE_FILE,
                required=True,
                description="음성 데이터",
            ),
        ],
        responses={400: "Invalid data in uploaded file", 200: "Success"},
    )
    @action(
        detail=False,
        methods=["post"],
        parser_classes=(MultiPartParser,),
        name="upload-voice-file",
        url_path="upload-voice-file",
    )
    def post(self, request, format=None):
        # 답변을 받고, 응답을 해주는 부분 -> 음성 파일 추출 필요
        # 오디오 파일, 지원 정보 아이디, 질문 아이디를 Request Body로 받음
        # audio_file = request.FILES["voice_file"]
        # form_id = request.data["form_id"]
        # question_id = request.data["question_id"]
        # transcript = openai.Audio.transcribe("whisper-1", audio_file)
        # transcription = transcript["text"]

        # S3에 업로드하는 로직 필요!
        
        # delay() : celery 작업 즉, 비동기적으로 작업 예
		# delay() 함수를 통해 tasks.py의 process_whisper_data를 실행
        transcription = process_whisper_data.delay()

        # 답변 테이블에 추가
        question_object = Question.objects.get(question_id=question_id)
        Answer.objects.create(content=transcription, question_id=question_object)

        form_info = Form.objects.get(id=form_id)
        questions = form_info.questions.all()

        # 기본 튜닝
        self.default_tuning()

        print(questions)
        # 질문, 대답 추가.
        for question in questions:
            answer = question.answer
            self.add_question_answer(question.content, answer.content)
            
        # =========================gpt_answer===============================      
        # 질문, 답변 텍스트 가져오기
        question = question_object.content
        answer = answer_object.content
        
        # gpt 모범 답변 튜닝 및 생성
        # gpt_answer = self.add_gptanswer(question, answer)
        gpt_answer = add_gptanswer(question, answer)
        
        # gpt 모범 답변 객체 생성
        gpt_object = GPTAnswer.objects.create(question_id=question_object, content=gpt_answer)
        # =========================gpt_answer===============================

        message = self.continue_conversation()

        # 질문 테이블에 정보 추가
        Question.objects.create(content=message, form_id=form_info)

        return Response(message, status=status.HTTP_200_OK)

    # 인성 면접 기본 튜닝
    def default_tuning(self):
        # 대화 시작 메시지 추가
        self.conversation.append(
            {
                "role": "system",
                "content": "You're a strict interviewer. You don't make any unnecessary expressions asides from giving interview questions.",
            }
        )
        self.conversation.append(
            {
                "role": "user",
                "content": 'function_name: [personality_interview] input: ["sector", "job", "career", "resume", "number_of_questions"] rule: [I want you to act as a strict interviewer, asking personality questions for the interviewee. I will provide you with input forms including "sector", "job", "career", "resume", and "number_of_questions". I have given inputs, but you do not have to refer to those. Your task is to simply make common personality questions and provide questions to me. You should create total of "number_of_questions" amount of questions, and provide it once at a time. You should ask the next question only after I have answered to the question. Do not include any explanations or additional information in your response, simply provide the generated question. You should also provide only one question at a time. Example questions would be questions such as "How do you handle stress and pressure?", "If you could change one thing about your personality, what would it be and why?". Remember, these questions are related to personality. Once all questions are done, you should just say "Alright. I will evaluate your answers." You must speak only in Korean during the interview.] personality_interview("IT", "Developer", "Fresher", "Graduated Tech University of Korea, Bachelor\'s degree of Software, has experience with Python Django REST framework.", "3")',
            }
        )

    # 질문과 대답 추가
    def add_question_answer(self, question, answer):
        self.conversation.append({"role": "assistant", "content": question})
        self.conversation.append({"role": "assistant", "content": answer})

    def continue_conversation(self):
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", messages=self.conversation, temperature=0.9, n=1
        )

        message = completion.choices[0].message["content"]
        return message


# 특정 form의 질문, 답변 가져오기(get으로 가져오기)
class QnAview(APIView):
    @swagger_auto_schema(
        operation_description="지원 정보와 연결된 질문, 답변 받기",
        operation_id="form_id를 입력해주세요.",
        manual_parameters=[
            openapi.Parameter(
                name="form_id",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="form_id",
            )
        ],
        responses={"200": ResponseVoiceSerializer},
    )
    # form_id와 연결되어 있는 question 객체를 가져온다.
    # form에 질문과 답변이 여러개 들어있으므로 모두 가져온 후 보여줄 수 있어야 한다.
    def get(self, request):
        form_id = request.GET.get("form_id")
        # form Object 얻기
        form_object = Form.objects.get(id=form_id)

        # 특정 form과 연결된 Question, Answer 객체 리스트로 얻기
        question_object = Question.objects.filter(form_id=form_object)

        QnA = []
        for i in range(0, len(question_object) - 1):  # ok
            answer_object = Answer.objects.get(question_id=question_object[i])  # ok

            # 질문, 답변 텍스트 가져오기
            question = question_object[i].content
            answer = answer_object.content

            QnA.append({"question": question, "answer": answer})

        # QnA 리스트 JSON으로 변환
        QnA = {"QnA": QnA}

        return JsonResponse(QnA, status=status.HTTP_200_OK)


class GPTAnswerview(APIView):
    @swagger_auto_schema(
        operation_description="지원 정보와 연결된 질문, 답변, GPT 답변 받기",
        operation_id="form_id를 입력해주세요.",
        manual_parameters=[
            openapi.Parameter(
                name="form_id",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                required=True,
                description="form_id",
            )
        ],
        responses={"200": ResponseVoiceSerializer},
    )
    def get(self, request):
        form_id = request.GET.get("form_id")
        # form Object 얻기
        form_object = Form.objects.get(id=form_id)

        # 특정 form과 연결된 Question 객체 리스트로 얻기
        question_object = Question.objects.filter(form_id=form_object)

        QnA = []
        for i in range(0, len(question_object) - 1):  # ok
            answer_object = Answer.objects.get(question_id=question_object[i])
            gptanswer_object = GPTAnswer.objects.get(question_id=question_object[i])

            # 질문, 답변 텍스트 가져오기
            question_content = question_id = question_object[i].content
            answer_content = answer_object.content
            gpt_answer = gptanswer_object.content

            QnA.append(
                {
                    "question": question_content,
                    "answer": answer_content,
                    "gptanswer": gpt_answer,
                }
            )

        # QnA 리스트 JSON으로 변환
        QnA = {"QnA": QnA}

        return JsonResponse(QnA, status=status.HTTP_200_OK)
