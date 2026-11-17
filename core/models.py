import json
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = (
        ('HOD', 'Head of Department (HOD)'),
        ('FACULTY', 'Faculty / Lecturer'),
        ('STUDENT', 'Student'),
    )
    BRANCH_CHOICES = (
        ('CSE', 'Computer Science & Engineering'),
        ('ME', 'Mechanical Engineering'),
        ('EE', 'Electrical Engineering'),
        ('CE', 'Civil Engineering'),
        ('ECE', 'Electronics Engineering'),
    )
    role = models.CharField(max_length=15, choices=ROLE_CHOICES, default='STUDENT')
    mobile = models.CharField(max_length=15, unique=True, null=True, blank=True)
    branch = models.CharField(max_length=10, choices=BRANCH_CHOICES, default='CSE')

    def __str__(self):
        return f"{self.username} ({self.role})"


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    enrollment_id = models.CharField(max_length=30, unique=True)
    semester = models.IntegerField(default=5)
    parent_mobile = models.CharField(max_length=15)
    face_encoding = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def set_encoding(self, embedding):
        if hasattr(embedding, 'tolist'):
            embedding = embedding.tolist()
        self.face_encoding = json.dumps(embedding)

    def get_encoding(self):
        if not self.face_encoding:
            return None
        return json.loads(self.face_encoding)

    def __str__(self):
        return f"{self.enrollment_id} - {self.user.get_full_name()}"


class FacultyProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='faculty_profile')
    employee_id = models.CharField(max_length=30, unique=True)
    designation = models.CharField(max_length=50, default='Lecturer')

    def __str__(self):
        return f"{self.employee_id} - {self.user.get_full_name()}"


class Subject(models.Model):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    branch = models.CharField(max_length=10, choices=User.BRANCH_CHOICES, default='CSE')
    semester = models.IntegerField(default=5)
    faculty = models.ForeignKey(FacultyProfile, on_delete=models.SET_NULL, null=True, related_name='subjects')

    def __str__(self):
        return f"{self.code} - {self.name}"


class WeeklyTimetable(models.Model):
    DAY_CHOICES = (
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
    )
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='timetable_slots')
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room_no = models.CharField(max_length=30, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['day_of_week', 'start_time']

    def __str__(self):
        return f"{self.subject.code} | {self.get_day_of_week_display()} ({self.start_time}-{self.end_time})"


class Attendance(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='attendances')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='attendances')
    timetable_slot = models.ForeignKey(WeeklyTimetable, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateField(auto_now_add=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    is_present = models.BooleanField(default=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    face_match_confidence = models.FloatField(default=0.0)

    class Meta:
        unique_together = ('student', 'timetable_slot', 'date')

    def __str__(self):
        return f"{self.student.enrollment_id} - {self.subject.code} ({self.date})"


class MidTermMarks(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='midterm_marks')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='midterm_marks')
    mid_term_1 = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(20.0)])
    mid_term_2 = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0.0), MaxValueValidator(20.0)])
    updated_by_hod = models.BooleanField(default=False)
    hod_remarks = models.CharField(max_length=255, blank=True, null=True)
    is_locked = models.BooleanField(default=False)
    last_modified = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'subject')

    @property
    def average_marks(self):
        if self.mid_term_1 is not None and self.mid_term_2 is not None:
            return round((self.mid_term_1 + self.mid_term_2) / 2, 2)
        if self.mid_term_1 is not None:
            return round(self.mid_term_1, 2)
        if self.mid_term_2 is not None:
            return round(self.mid_term_2, 2)
        return "-"


class StudyNote(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='notes')
    uploaded_by = models.ForeignKey(FacultyProfile, on_delete=models.SET_NULL, null=True)
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='study_notes/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.subject.code} - {self.title}"


class Notice(models.Model):
    CATEGORY_CHOICES = (
        ('BTER', 'BTER Jodhpur Exam/Policy'),
        ('COLLEGE', 'GPC Bundi General Notice'),
        ('TIMETABLE', 'Class / Lecture Schedule'),
        ('ALERT', 'Urgent / Attendance Alert'),
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='COLLEGE')
    target_semester = models.IntegerField(null=True, blank=True)
    posted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title