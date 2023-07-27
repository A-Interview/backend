from __future__ import absolute_import, unicode_literals
from celery import shared_task
import openai
import os
from dotenv import load_dotenv
import boto3
import tempfile
from urllib.parse import urlparse

load_dotenv()
openAI_Api_key = os.environ.get('GPT_API_KEY')
openai.api_key = openAI_Api_key
# @app.task
@shared_task
def process_whisper_data(audio_file_url):
        # S3에서 file_key를 가져오기
        parsed_url = urlparse(audio_file_url)
        audio_file_key = parsed_url.path.lstrip("/")
        
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

        except Exception as e:
                # 오류 처리
                print(f"오류 발생: {e}")
                return "파일을 불러올 수 없습니다."
        
        # audio_file = byte 객체 -> name 속성이 존재하지 않아서 whisper에서 받을 수 없음
        # 이 문제를 회피하기 위해서 name 속성이 존재하는 tempfile로 만든 후 whisper에게 전달
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temp_file_path = temp_file.name
        
        # 임시 음성 파일 생성
        with open(temp_file_path, "wb") as file:
                file.write(audio_file)
        
        # 임시 음성 파일을 whisper에게 전달해서 텍스트 파일로 반환
        with open(temp_file_path, "rb") as temp_file:
                transcript = openai.Audio.transcribe("whisper-1", temp_file)
        transcription = transcript['text']
        
        temp_file.close()

        # 임시 파일 삭제
        os.unlink(temp_file_path)
        
        return transcription