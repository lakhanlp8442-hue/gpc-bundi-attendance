from django.contrib import admin
from .models import (
    User, StudentProfile, FacultyProfile, Subject,
    WeeklyTimetable, Attendance, MidTermMarks, StudyNote, Notice
)

admin.site.register([
    User, StudentProfile, FacultyProfile, Subject,
    WeeklyTimetable, Attendance, MidTermMarks, StudyNote, Notice
])