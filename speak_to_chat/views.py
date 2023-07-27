from urllib.parse import urlparse

import boto3
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

from .models import Question
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
import random
from django.http import HttpResponse
from django.http import JsonResponse

from .tasks import process_whisper_data
from forms.models import Form

load_dotenv()
openai.api_key = os.getenv("GPT_API_KEY")

# 특정 form의 질문, 답변, 음성파일 가져오기
class QnAview(APIView):
    @swagger_auto_schema(
        operation_description="지원 정보와 연결된 질문, 답변, 음성파일 받기",
        operation_id="질문, 답변, 음성파일 요청",
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
        for i in range(0, len(question_object)):  # ok
            question_id = question_object[i].question_id

            answer_object = Answer.objects.get(question_id=question_object[i])  # ok

            # 질문, 답변내용, 음성파일 가져오기
            question = question_object[i].content
            answer = answer_object.content
            audio_file_url = answer_object.recode_file

            #s3로부터 음성파일 받아오기
            record_data = self.get_record(audio_file_url)

            QnA.append({"question_id": question_id, "question": question, "answer": answer, "record": record_data})

        # QnA 리스트 JSON으로 변환
        QnA = {"QnA": QnA}

        return JsonResponse(QnA, status=status.HTTP_200_OK)

    def get_record(self, audio_file_url):

        # S3에서 audio_file_key를 가져오기
        parsed_url = urlparse(audio_file_url)
        audio_file_key = parsed_url.path.lstrip("/")

        # AWS SDK 클라이언트 생성:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=os.environ.get("MY_AWS_ACCESS_KEY"),
            aws_secret_access_key=os.environ.get("MY_AWS_SECRET_ACCESS_KEY"),
        )

        try:
            # 음성 파일 객체를 S3 버킷에서 가져오기
            response = s3_client.get_object(Bucket=os.environ.get("AWS_STORAGE_BUCKET_NAME"), Key=audio_file_key)

            # 음성 파일 객체로부터 음성 파일 추출
            audio_file = response['Body'].read()

            # 음성 파일을 Base64로 인코딩하여 문자열로 변환
            encoded_data = base64.b64encode(audio_file).decode('utf-8')

            return encoded_data

        except Exception as e:
            # 오류 처리
            print(f"오류 발생: {e}")
            return "파일을 불러올 수 없습니다."


class GPTAnswerView(APIView):

    # POST: GPT 답변 생성하기
    @swagger_auto_schema(
        operation_description="GPT 답변 생성 및 저장",
        operation_id="GPT 답변 생성 및 저장",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'question_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='question_id 입력'),
            },
        ),
        responses={
            201: openapi.Response(description="GPT 답변 생성 완료"),
            400: "Bad request",
        },
    )
    def post(self, request, *args, **kwargs):
        question_id = request.data.get("question_id")
        question = get_object_or_404(Question, question_id=question_id)

        # generate_gpt_answer 메소드 불러오기
        gpt_answer_content = self.generate_gpt_answer(question.content)

        # GPTAnswer 생성 후 저장
        gpt_answer = GPTAnswer(content=gpt_answer_content, question_id=question)
        gpt_answer.save()

        return Response({"message": "GPT 답변 생성 완료"}, status=status.HTTP_201_CREATED)

    # GPT 답변 생성 메소드
    def generate_gpt_answer(self, question_content):
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an interviewee applying for the job. You must answer the given question just like an interviewee does. You must provide answer in Korean only."},
                {"role": "user", "content": question_content},
            ],
        )

        gpt_answer_content = response['choices'][0]['message']['content']

        return gpt_answer_content


    # GET: question_id에 해당하는 gpt_answer 불러오기
    @swagger_auto_schema(
        operation_description="질문에 해당되는 GPTAnswer 불러오기 (사전 생성 필수)",
        operation_id="GPTAnswer 가져오기",
        manual_parameters=[openapi.Parameter('question_id', openapi.IN_QUERY, description="ID of the question",
                                             type=openapi.TYPE_INTEGER)],
        responses={
            200: openapi.Response(description="GPTAnswer 반환 성공"),
            404: "question_id가 존재하지 않습니다.",
        },
    )
    def get(self, request, *args, **kwargs):
        question_id = request.query_params.get("question_id")
        question = get_object_or_404(Question, question_id=question_id)

        # question_id에 해당되는 gpt_answer 불러오기
        gpt_answer = get_object_or_404(GPTAnswer, question_id=question)

        return Response({"gpt_answer_content": gpt_answer.content}, status=status.HTTP_200_OK)