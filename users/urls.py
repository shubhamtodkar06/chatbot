# users/urls.py
from django.urls import path
from .views import SignupView, LoginView, signup_page, login_page

urlpatterns = [
    path('signup/', SignupView.as_view(), name='signup'),
    path('login/', LoginView.as_view(), name='login'),
    path('register/', signup_page, name='register_page'),  
    path('', login_page, name='signin_page'),
]