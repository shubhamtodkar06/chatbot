# Generated by Django 5.1.7 on 2025-04-02 10:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0003_rename_chatbot_response_chathistory_content_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='chathistory',
            name='session_id',
        ),
        migrations.AddField(
            model_name='chathistory',
            name='thread_id',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
