from rest_framework import serializers
from .models import ChatSession, Message


class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = ('id', 'title', 'created_at')


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ('id', 'role', 'content', 'has_paper_evidence',
                  'weak_evidence', 'paper_score', 'paper_sources', 'created_at')


class AskRequestSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=1000)
    session_id = serializers.IntegerField(required=False, allow_null=True)