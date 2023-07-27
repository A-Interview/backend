from drf_yasg.utils import swagger_auto_schema
from rest_framework import status, generics
from rest_framework.parsers import JSONParser, FileUploadParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from drf_yasg import openapi
from storage import get_file_url


from .serializers import RegisterSerializer, LoginSerializer, RefreshTokenSerializer
from django.contrib.auth import get_user_model

from rest_framework.decorators import action
from urllib.parse import urlparse


# 유저 모델 불러오기
User = get_user_model()

# 회원가입
class RegisterView(APIView):
    parser_classes = [JSONParser]
    serializer_class = RegisterSerializer

    @swagger_auto_schema(
        request_body=RegisterSerializer,
        operation_id="회원 가입",
        responses={200: RegisterSerializer(many=False)}
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            if user:
                return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# 로그인
class LoginView(generics.GenericAPIView):
    parser_classes = [JSONParser]
    serializer_class = LoginSerializer

    @swagger_auto_schema(operation_id="사용자 로그인")
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)

        # refresh token, access token
        return Response({
            'user_id': user.id,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        })

# 로그아웃
class LogoutView(APIView):
    parser_classes = [JSONParser]
    @swagger_auto_schema(
        request_body=RefreshTokenSerializer,
        operation_id="로그아웃 (토큰 blacklist)"
    )
    def post(self, request):
        try:
            refresh_token = request.data['refresh']
            token = RefreshToken(refresh_token)
            # 로그아웃 시 해당 token을 blacklist해서 auth를 위해 사용 불가하게 만든다.
            token.blacklist()

            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response(str(e), status=status.HTTP_400_BAD_REQUEST)

# soft-delete
class DeleteUserView(generics.DestroyAPIView):
    queryset = User.objects.all()
    lookup_field = 'id'

    @swagger_auto_schema(
        operation_id="회원 탈퇴",
    )
    def delete(self, request, *args, **kwargs):
        user = self.get_object()
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)



# 프로필 사진 입력
class UploadProfilePictureView(APIView):
    parser_classes = [MultiPartParser]
    
    @swagger_auto_schema(
        # API 작업에 대한 설명
        operation_description="프로필 사진 GET",
        operation_id="프로필 사진 가져오기",
        manual_parameters=[
            openapi.Parameter(
                name="pk", # 파일의 이름
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_INTEGER,
                description="사용자 pk",
            )],
        responses={400: "사진 조회에 실패했습니다.", 200: "조회 성공."}
    )
    def get(self, request):
        # 일반적으로 DRF를 사용하는 APIView나 ViewSet에서는 request.query_params를 사용하는 것이 좋습니다. 이유는 DRF의 request.query_params는 문자열로 변환된 쿼리 매개변수 값을 원래의 데이터 타입으로 변환하는 기능을 제공하기 때문입니다. 예를 들어, 쿼리 매개변수가 숫자인 경우에는 자동으로 정수로 변환하거나, 리스트인 경우에는 자동으로 리스트로 변환해줍니다. 이렇게 하면 매개변수 값을 더 쉽게 처리할 수 있습니다.
        user_id = request.query_params.get("pk") # 더 바람직(Django Rest Framework(DRF)에서 제공하는 request.query_params 딕셔너리)
        # user_id = request.GET.get("pk") -> 얘도 가능함(Django의 request.GET 딕셔너리)
        try:
            user = User.objects.get(id=user_id)
            # 프로필 사진이 등록되어 있다면
            if user.profile_picture:
                image_file_url = user.profile_picture
                return Response(image_file_url, status=status.HTTP_200_OK)
            else:
                return Response("프로필 사진이 없습니다.", status=400)
        except User.DoesNotExist:
            return Response("사용자를 찾을 수 없습니다.", status=400)
        

    image_param = openapi.Parameter(
        name="picture", # 파일의 이름
        in_=openapi.IN_FORM,
        type=openapi.TYPE_FILE,
        description="이미지 파일",
    )
    email_param = openapi.Parameter(
        name="pk", # 파일의 이름
        in_=openapi.IN_FORM,
        type=openapi.TYPE_INTEGER,
        description="사용자 pk",
    )

    @swagger_auto_schema(
        # API 작업에 대한 설명
        operation_description="프로필 사진 POST",
        operation_id="프로필 사진 업로드",
        # request_body=None,
        manual_parameters=[image_param, email_param],
        responses={400: "업로드에 실패했습니다.", 200: "성공적으로 업로드되었습니다."}
    )
    # @action : Django ViewSet에서 사용되며, 특정 작업에 대한 추가적인 액션을 정의할 때 사용
    @action(
        detail=False,
        methods=["post"],
        parser_classes=(MultiPartParser,),
        name="upload-image-file",
        url_path="upload-image-file",
    )
    # 사용자를 특정할 수 있는 정보(이메일..)이 필요한데 어떻게 받지 ?
    def post(self, request):
        # 사용자로부터 프로필 사진을 입력 받음
        image_file = request.FILES["picture"]
        user_info = request.data["pk"]
        
        # 사용자 객체 생성
        user = User.objects.get(id=user_info)
        
        # s3에 파일 업로드 후 url 반환
        image_file_url = get_file_url("image", image_file)
        
        # 사용자의 profile_picture 필드에 프로필 사진 url 삽입 및 저장
        user.profile_picture = image_file_url
        user.save()
        return Response(status=status.HTTP_204_NO_CONTENT)