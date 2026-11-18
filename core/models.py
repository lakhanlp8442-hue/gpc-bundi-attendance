import json
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = (
        ('STUDENT', 'Student'),
        ('FACULTY', 'Faculty'),
        ('HOD', 'Head of Department (HOD)'),
    )
    BRANCH_CHOICES = (
        ('CSE', 'Computer Science & Engineering'),
        ('ME', 'Mechanical Engineering'),
        ('CE', 'Civil Engineering'),
        ('EE', 'Electrical Engineering'),
        ('EL', 'Electronics Engineering'),
    )
    role = models.CharField(max_length=15, choices=ROLE_CHOICES, default='STUDENT')
    mobile = models.CharField(max_length=15, unique=True)
    branch = models.CharField(max_length=10, choices=BRANCH_CHOICES, default='CSE')

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.role})"


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    enrollment_id = models.CharField(max_length=25, unique=True, help_text="BTER Roll/Enrollment No.")
    semester = models.IntegerField(choices=[(i, f"Semester {i}") for i in range(1, 7)], default=5)
    parent_mobile = models.CharField(max_length=15, blank=True, null=True, default="")
    face_encoding = models.TextField(blank=True, null=True)
    fingerprint_template = models.TextField(blank=True, null=True)

    def set_encoding(self, encoding_list):
        self.face_encoding = json.dumps(encoding_list)

    def get_encoding(self):
        return json.loads(self.face_encoding) if self.face_encoding else None

    def set_fingerprint(self, iso_b64):
        self.fingerprint_template = iso_b64

    def get_fingerprint(self):
        return self.fingerprint_template

    def __str__(self):
        return f"{self.enrollment_id} - {self.user.get_full_name()}"


class FacultyProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='faculty_profile')
    employee_id = models.CharField(max_length=25, unique=True)
    designation = models.CharField(max_length=50, default="Lecturer")

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.designation})"


class Subject(models.Model):
    code = models.CharField(max_length=15, unique=True, help_text="e.g., CS-501")
    name = models.CharField(max_length=100)
    branch = models.CharField(max_length=10, choices=User.BRANCH_CHOICES, default='CSE')
    semester = models.IntegerField(choices=[(i, f"Semester {i}") for i in range(1, 7)])
    faculty = models.ForeignKey(FacultyProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='subjects')

    def __str__(self):
        return f"{self.code}: {self.name} (Sem {self.semester})"


class WeeklyTimetable(models.Model):
    DAYS_OF_WEEK = (
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
    )
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='timetable_slots')
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room_no = models.CharField(max_length=20, blank=True, null=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['day_of_week', 'start_time']

    def __str__(self):
        return f"{self.subject.code} - {self.get_day_of_week_display()} ({self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')})"


class Attendance(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='attendances')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='attendances')
    timetable_slot = models.ForeignKey(WeeklyTimetable, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateField(auto_now_add=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    is_present = models.BooleanField(default=True)
    latitude = models.FloatField(null=True, blank=True, default=0.0)
    longitude = models.FloatField(null=True, blank=True, default=0.0)
    face_match_confidence = models.FloatField(default=0.0)

    class Meta:
        unique_together = ('student', 'timetable_slot', 'date')

    def __str__(self):
        return f"{self.student.enrollment_id} | {self.subject.code} | {self.date}"


class MidTermMarks(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='marks')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='marks')
    mid_term_1 = models.FloatField(null=True, blank=True)
    mid_term_2 = models.FloatField(null=True, blank=True)
    max_marks = models.FloatField(default=20.0)
    updated_by_hod = models.BooleanField(default=False)
    hod_remarks = models.CharField(max_length=255, blank=True, null=True, default="")
    is_locked = models.BooleanField(default=False)

    class Meta:
        unique_together = ('student', 'subject')

    @property
    def average_marks(self):
        scores = [m for m in (self.mid_term_1, self.mid_term_2) if m is not None]
        return round(sum(scores) / len(scores), 2) if scores else 0.0


class StudyNote(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='notes')
    uploaded_by = models.ForeignKey(FacultyProfile, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True, null=True, default="")
    file = models.FileField(upload_to='study_notes/')
    uploaded_at = models.DateTimeField(auto_now_add=True)


class Notice(models.Model):
    CATEGORY_CHOICES = (
        ('BTER', 'BTER Jodhpur Circular'),
        ('COLLEGE', 'GPC Bundi Notice'),
        ('ALERT', 'Urgent / Exam Alert'),
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    category = models.CharField(max_length=15, choices=CATEGORY_CHOICES, default='COLLEGE')
    target_semester = models.IntegerField(null=True, blank=True, help_text="Blank means all semesters")
    posted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']