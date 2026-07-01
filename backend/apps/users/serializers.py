from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import CustomUser


class RegisterSerializer(serializers.ModelSerializer): #  serializes all user data including password --> always implement in a User app
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True, label="Confirm password")

    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'password', 'password2')

    def validate(self, attrs): #Serializer class method - password validation after username, email and other fields besides password/password 2 have been validated
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    def create(self, validated_data): #how validated data is used to create user
        validated_data.pop('password2')
        user = CustomUser.objects.create_user(**validated_data)  #create_user() hashes password before storing
        return user


class UserSerializer(serializers.ModelSerializer): #useful for a "profile" endpoint (displaying user info) b/c password is not exposed
    class Meta:
        model = CustomUser
        fields = ('id', 'username', 'email')
