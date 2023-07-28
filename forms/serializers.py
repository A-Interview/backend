from rest_framework import serializers

from speak_to_chat.serializers import ResponseVoiceSerializer
from users.models import User
from .models import Form, Qes_Num


class FormsSerializer(serializers.ModelSerializer):
    class Meta:
        #user_id = serializers.PrimaryKeyRelatedField(read_only=True)
        model = Form
        fields = '__all__'
        def __str__(self):
            return f"{Form.sector_name} in {Form.job_name}"

class FormCreateSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField()
    class Meta:
        model = Form
        fields = ("id", "sector_name", "job_name", "career", "resume")

class FormsPutSerializer(serializers.ModelSerializer):
    sector_name = serializers.CharField(max_length=100, required=False)
    job_name = serializers.CharField(max_length=100, required=False)
    resume = serializers.CharField(max_length=10000, required=False)
    class Meta:
        model = Form
        fields = ("sector_name", "job_name", "career", "resume")

class QesNumSerializer(serializers.ModelSerializer):
    qesnum_id = serializers.ReadOnlyField()
    class Meta:
        model = Qes_Num
        fields = '__all__'


