from django.http import JsonResponse
from drf_yasg import openapi
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404, redirect, render
from drf_yasg.utils import swagger_auto_schema
from forms.serializers import FormsSerializer, FormCreateSerializer, FormsPutSerializer, QesNumSerializer
from forms.models import Form, Qes_Num

from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed

from users.models import User


# Create your views here.

# 지원정보 API
class FormsAllView(APIView):
    # 사용자 토큰인증
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    parameter_token = openapi.Parameter(
        "Authorization",
        openapi.IN_HEADER,
        description="access_token",
        type=openapi.TYPE_STRING,
    )

    @swagger_auto_schema(
        manual_parameters=[parameter_token],
        operation_id="사용자의 지원정보 전체조회",
    )
    def get(self, request, user_id):
        data = Form.objects.filter(user_id=user_id)
        serializer = FormsSerializer(data, many=True)
        return Response(serializer.data, status=200)


    # 지원정보 추가
    @swagger_auto_schema(
        request_body=FormCreateSerializer,
        manual_parameters=[parameter_token],
        operation_id="사용자 지원정보 추가",
    )
    def post(self, request, user_id):
        try:
            user = self.request.user  # JWTAuthentication을 통해 인증된 사용자 인스턴스를 가져옴
        except AuthenticationFailed:
            # 토큰이 유효하지 않거나 인증되지 않은 경우에 대한 처리를 수행
            return Response("인증에 실패했습니다.", status=401)

        serializer = FormCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user_id=user)
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=404)


class FormsUserView(APIView):

    # 사용자별 지원정보 상세조회
    @swagger_auto_schema(operation_id="지원서 id로 form 조회")
    def get(self, request, pk):
        form_obj = Form.objects.filter(id=pk)
        serializer = FormsSerializer(form_obj, many=True)
        return Response(serializer.data)

    # 지원정보 삭제
    @swagger_auto_schema(operation_id="지원서 id로 form 삭제")
    def delete(self, request, pk):
        info = get_object_or_404(Form, id=pk)
        info.delete()
        return JsonResponse({'message': 'Form deleted successfully.'})
        #return redirect("form_list")


    # 지원정보 수정
    @swagger_auto_schema(
        request_body=FormsPutSerializer,
        operation_id="지원서 id로 form 수정",
    )
    def put(self, request, pk):
        info = get_object_or_404(Form, pk=pk)
        serializer = FormsSerializer(info, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=404)

class QesNumView(APIView):
    @swagger_auto_schema(
        operation_id="면접 질문 개수 요청",
    )
    def get(self, request, form_id):
        qes_num = get_object_or_404(Qes_Num, form_id=form_id)
        serializer = QesNumSerializer(qes_num)
        return Response(serializer.data)

class QesNumPostView(APIView):
    @swagger_auto_schema(
        request_body=QesNumSerializer,
        operation_id="면접 질문 개수 저장",
    )
    def post(self, request):
        # form_id = request.data.get("form_id")
        serializer = QesNumSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)
        return Response(serializer.errors, status=404)
