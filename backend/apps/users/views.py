from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import status
from .serializers import RegisterSerializer, UserSerializer
# Create your views here.
@api_view(['POST'])
@permission_classes([AllowAny]) # registration must be public; default permission is IsAuthenticated
def register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save() # calls create_user() --> regular (non-superuser) account
    return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def is_Authenticated(request):
    content = {
        "message": "You are authenticated brother",
    }
    return Response(content, status = status.HTTP_200_OK)