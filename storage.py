import os
import boto3
from dotenv import load_dotenv
import uuid

def get_file_url(file_type, file):
    load_dotenv()
    # AWS SDK 클라이언트 생성:
    s3_client = boto3.client(
        's3',
        aws_access_key_id=os.environ.get("MY_AWS_ACCESS_KEY"),
        aws_secret_access_key=os.environ.get("MY_AWS_SECRET_ACCESS_KEY"),
    )
    
    # 음성 녹음 파일(audio)인 경우
    if file_type == "audio":
        file_key = "record/" + str(uuid.uuid4()) + ".mp3"
    # 프로필 이미지 파일(image)인 경우(s3 디렉토리 추가 후 수정해야 함)
    else:
        file_key = "profile_image/" + str(uuid.uuid4()) + ".jpg"
        
    

    # 파일을 S3 버킷에 업로드
    s3_client.put_object(Body=file, Bucket=os.environ.get("AWS_STORAGE_BUCKET_NAME"), Key=file_key)
    # 업로드된 파일의 URL을 구성
    url = os.getenv("FILE_URL")+"/"+ file_key

    # URL 문자열에서 공백을 "_"로 대체
    url = url.replace(" ", "_")
    
    return url