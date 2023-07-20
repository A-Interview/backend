

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('speak_to_chat', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='GPTAnswer',
            fields=[
                ('gptanswer_id', models.AutoField(db_column='question_id', primary_key=True, serialize=False)),
                ('content', models.TextField()),
                ('recode_file', models.CharField(max_length=200)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(blank=True, null=True)),
                ('question_id', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='gptanswer', to='speak_to_chat.question')),
            ],
            options={
                'db_table': 'gptanswer',
            },
        ),
    ]