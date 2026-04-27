import json
import os
import sys

from django.http import StreamingHttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import serializers as drf_serializers

from .models import ChatSession, Message
from .serializers import ChatSessionSerializer, MessageSerializer, AskRequestSerializer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.rag_service import HybridRAGService

_rag = None


def get_rag():
    global _rag
    if _rag is None:
        _rag = HybridRAGService()
    return _rag


class ChatSessionListView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ChatSessionSerializer

    @extend_schema(tags=['chat'], responses={200: ChatSessionSerializer(many=True)})
    def get(self, request, *args, **kwargs):
        sessions = ChatSession.objects.filter(user=request.user).order_by('-created_at')
        serializer = ChatSessionSerializer(sessions, many=True)
        return Response(serializer.data)

    @extend_schema(tags=['chat'], responses={201: ChatSessionSerializer})
    def post(self, request, *args, **kwargs):
        title = request.data.get('title', '새 채팅')
        session = ChatSession.objects.create(user=request.user, title=title)
        serializer = ChatSessionSerializer(session)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ChatSessionDetailView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = ChatSessionSerializer

    @extend_schema(tags=['chat'], responses={204: None})
    def delete(self, request, session_id, *args, **kwargs):
        try:
            session = ChatSession.objects.get(id=session_id, user=request.user)
            session.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except ChatSession.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)


class MessageListView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = MessageSerializer

    @extend_schema(tags=['chat'], responses={200: MessageSerializer(many=True)})
    def get(self, request, session_id, *args, **kwargs):
        try:
            session = ChatSession.objects.get(id=session_id, user=request.user)
            messages = session.messages.order_by('created_at')
            serializer = MessageSerializer(messages, many=True)
            return Response(serializer.data)
        except ChatSession.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)


class HealthView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = drf_serializers.Serializer

    @extend_schema(tags=['rag'], responses={200: None})
    def get(self, request, *args, **kwargs):
        try:
            counts = get_rag().get_collection_counts()
            return Response({'status': 'ok', 'collections': counts})
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=500)


class AskView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = drf_serializers.Serializer

    @extend_schema(tags=['rag'], request=AskRequestSerializer, responses={200: None})
    def post(self, request, *args, **kwargs):
        question = request.data.get('question', '')
        session_id = request.data.get('session_id')

        if not question:
            return Response({'error': '질문을 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = get_rag().ask(question)

            if session_id:
                try:
                    session = ChatSession.objects.get(id=session_id, user=request.user)
                    Message.objects.create(session=session, role='user', content=question)
                    Message.objects.create(
                        session=session,
                        role='assistant',
                        content=result.answer,
                        has_paper_evidence=result.has_paper_evidence,
                        weak_evidence=result.weak_evidence,
                        paper_score=result.paper_score,
                        paper_sources=[s.dict() for s in result.paper_sources],
                    )
                except ChatSession.DoesNotExist:
                    pass

            return Response(result.dict())

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AskStreamView(generics.GenericAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = drf_serializers.Serializer

    @extend_schema(tags=['rag'], request=AskRequestSerializer, responses={200: None})
    def post(self, request, *args, **kwargs):
        question = request.data.get('question', '')
        session_id = request.data.get('session_id')

        if not question:
            return Response({'error': '질문을 입력해주세요.'}, status=status.HTTP_400_BAD_REQUEST)

        async def event_stream():
            full_answer = ''
            final_event = None

            async for event in get_rag().ask_stream(question):
                if event['type'] == 'chunk':
                    full_answer += event.get('text', '')
                if event['type'] == 'done':
                    final_event = event
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            if session_id and final_event:
                try:
                    session = ChatSession.objects.get(id=session_id, user=request.user)
                    Message.objects.create(session=session, role='user', content=question)
                    Message.objects.create(
                        session=session,
                        role='assistant',
                        content=full_answer,
                        has_paper_evidence=final_event.get('has_paper_evidence', False),
                        weak_evidence=final_event.get('weak_evidence', False),
                        paper_score=final_event.get('paper_score', 0.0),
                        paper_sources=final_event.get('paper_sources', []),
                    )
                except ChatSession.DoesNotExist:
                    pass

        return StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
        )