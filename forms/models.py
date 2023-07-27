from django.db import models
from users.models import User


class Form(models.Model):
    user_id = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="forms", db_column="user_id"
    )
    sector_name = models.CharField(max_length=100, null=False)
    job_name = models.CharField(max_length=100, null=False)
    career = models.CharField(max_length=20, default="신입", null=False)
    resume = models.CharField(max_length=10000, null=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(blank=True, null=True)
    def __str__(self):
        return f"{self.job_name} in {self.sector_name}"

class Qes_Num(models.Model):
    qesnum_id = models.AutoField(primary_key=True, db_column="qesnum_id")
    form_id = models.ForeignKey(
        Form, on_delete=models.CASCADE, related_name="qes_num", db_column="form_id"
    )
    default_que_num=models.IntegerField(null=False)
    situation_que_num = models.IntegerField(null=False)
    deep_que_num = models.IntegerField(null=False)
    personality_que_num = models.IntegerField(null=False)
    total_que_num = models.IntegerField(null=False)

    class Meta:
        db_table = "qes_num"

