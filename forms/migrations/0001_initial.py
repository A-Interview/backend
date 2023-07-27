# Generated by Django 4.2.3 on 2023-07-27 08:02

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Form',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sector_name', models.CharField(max_length=100)),
                ('job_name', models.CharField(max_length=100)),
                ('career', models.CharField(default='신입', max_length=20)),
                ('resume', models.CharField(max_length=10000)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='Qes_Num',
            fields=[
                ('qesnum_id', models.AutoField(db_column='qesnum_id', primary_key=True, serialize=False)),
                ('default_que_num', models.IntegerField()),
                ('situation_que_num', models.IntegerField()),
                ('deep_que_num', models.IntegerField()),
                ('personality_que_num', models.IntegerField()),
                ('total_que_num', models.IntegerField()),
                ('form_id', models.ForeignKey(db_column='form_id', on_delete=django.db.models.deletion.CASCADE, related_name='qes_num', to='forms.form')),
            ],
            options={
                'db_table': 'qes_num',
            },
        ),
    ]
