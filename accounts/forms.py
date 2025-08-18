# accounts/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model

User = get_user_model() # Получаем вашу кастомную модель пользователя

class UserRegisterForm(UserCreationForm):
    """
    Форма регистрации пользователя, основанная на встроенной UserCreationForm.
    Использует вашу кастомную модель User.
    """
    class Meta:
        model = User
        fields = ('username',) # Или 'login', если вы используете его вместо username

    # Можно добавить дополнительные поля, если они есть в вашей модели User
    # Например:
    # email = forms.EmailField(required=True)

    # Если вы хотите, чтобы email был уникальным
    # def clean_email(self):
    #     email = self.cleaned_data.get('email')
    #     if User.objects.filter(email=email).exists():
    #         raise forms.ValidationError("Пользователь с таким email уже существует.")
    #     return email

class UserLoginForm(AuthenticationForm):
    """
    Форма для входа пользователя. Использует встроенную AuthenticationForm.
    """
    # Если вы используете 'login' вместо 'username' для входа, то вам может потребоваться
    # переопределить поле username на login
    # username = forms.CharField(label='Логин', max_length=150)
    pass