from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_redirect, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/student/', views.student_register_view, name='student_register'),
    path('register/faculty/', views.faculty_register_view, name='faculty_register'),

    path('dashboard/student/', views.student_dashboard, name='student_dashboard'),
    path('dashboard/faculty/', views.faculty_dashboard, name='faculty_dashboard'),
    path('dashboard/hod/', views.hod_dashboard, name='hod_dashboard'),

    path('api/attendance/mark/', views.mark_face_attendance_api, name='mark_face_attendance_api'),
    path('api/face/re-register/', views.re_register_face_api, name='re_register_face_api'),
    path('api/fingerprint/register/', views.register_fingerprint_api, name='register_fingerprint_api'),
    path('api/fingerprint/mark/', views.mark_fingerprint_attendance_api, name='mark_fingerprint_attendance_api'),
]