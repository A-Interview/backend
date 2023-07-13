# 베이스 이미지 정의
FROM python:3.9

# 작업 디렉토리 생성 및 설정
WORKDIR /app

# 필요한 패키지 설치
RUN pip install --upgrade pip
COPY requirements.txt .
RUN pip install -r requirements.txt

# 소스 코드 복사
COPY . .

# Django 프로젝트 실행
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]