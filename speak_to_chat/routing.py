from django.urls import path, re_path
from .deep_interview_consumer import DeepInterviewConsumer
from .situation_interview_consumer import SituationInterviewConsumer

websocket_urlpatterns = [
    re_path(r"ws/deep-interview/$", DeepInterviewConsumer.as_asgi()),
    re_path(r"ws/situation-interview/$", SituationInterviewConsumer.as_asgi()),
]