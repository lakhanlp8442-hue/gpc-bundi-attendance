import datetime
import json
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .mantra_scanner import (
    capture_mfs100_fingerprint,
    verify_mfs100_fingerprint,
)
from .models import (
    Attendance, FacultyProfile, MidTermMarks, Notice,
    StudentProfile, StudyNote, Subject, User, WeeklyTimetable
)
from .utils import (
    build_low_attendance_whatsapp_url,
    build_student_low_attendance_whatsapp_url,
    extract_face_embedding,
    verify_campus_geofence,
    verify_face_match,
)

ATTENDANCE_WINDOW_MINUTES = 15  # Lecture start hone ke baad kitne minute tak attendance open rahegi


def is_slot_open_for_attendance(slot, now_dt):
    start_dt = datetime.datetime.combine(now_dt.date(), slot.start_time)
    end_dt = datetime.datetime.combine(now_dt.date(), slot.end_time)
    cutoff_dt = min(start_dt + datetime.timedelta(minutes=ATTENDANCE_WINDOW_MINUTES), end_dt)
    return start_dt <= now_dt <= cutoff_dt


def home_redirect(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.user.is_superuser or request.user.role == 'HOD':
        return redirect('hod_dashboard')
    elif request.user.role == 'FACULTY' and hasattr(request.user, 'faculty_profile'):
        return redirect('faculty_dashboard')
    elif request.user.role == 'STUDENT' and hasattr(request.user, 'student_profile'):
        return redirect('student_dashboard')

    logout(request)
    messages.warning(request, "Account profile incomplete. Please register properly.")
    return redirect('login')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')
        messages.error(request, "Invalid Enrollment/Employee ID or Password.")
    return render(request, 'auth/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


def student_register_view(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        enrollment_id = request.POST.get('enrollment_id', '').strip().upper()
        email = request.POST.get('email', '').strip()
        mobile = request.POST.get('mobile', '').strip()
        parent_mobile = request.POST.get('parent_mobile', '').strip()
        branch = request.POST.get('branch', 'CSE')
        semester = int(request.POST.get('semester', 5))
        password = request.POST.get('password', '')
        face_image_b64 = request.POST.get('face_image', '')

        if StudentProfile.objects.filter(enrollment_id=enrollment_id).exists() or User.objects.filter(username=enrollment_id).exists():
            messages.error(request, f"BTER Enrollment ID '{enrollment_id}' already registered!")
            return redirect('student_register')

        if User.objects.filter(mobile=mobile).exists():
            messages.error(request, "This student mobile number is already registered.")
            return redirect('student_register')

        if not face_image_b64:
            messages.error(request, "Live Face Capture is mandatory.")
            return redirect('student_register')

        embedding, err = extract_face_embedding(face_image_b64)
        if err:
            messages.error(request, f"Face Error: {err}")
            return redirect('student_register')

        try:
            with transaction.atomic():
                first_name, *last_parts = full_name.split(' ', 1)
                user = User.objects.create_user(
                    username=enrollment_id,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_parts[0] if last_parts else '',
                    role='STUDENT',
                    mobile=mobile,
                    branch=branch,
                )
                profile = StudentProfile(
                    user=user,
                    enrollment_id=enrollment_id,
                    semester=semester,
                    parent_mobile=parent_mobile,
                )
                profile.set_encoding(embedding)
                profile.save()
            messages.success(request, f"Registration successful for {enrollment_id}! Please login.")
            return redirect('login')
        except IntegrityError:
            messages.error(request, "Database error: Mobile number or Enrollment ID already exists.")
    return render(request, 'auth/student_register.html')


def faculty_register_view(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        employee_id = request.POST.get('employee_id', '').strip().upper()
        email = request.POST.get('email', '').strip()
        mobile = request.POST.get('mobile', '').strip()
        branch = request.POST.get('branch', 'CSE')
        designation = request.POST.get('designation', 'Lecturer')
        password = request.POST.get('password', '')

        if FacultyProfile.objects.filter(employee_id=employee_id).exists() or User.objects.filter(username=employee_id).exists():
            messages.error(request, "Faculty ID already registered.")
            return redirect('faculty_register')

        if User.objects.filter(mobile=mobile).exists():
            messages.error(request, "This mobile number is already registered.")
            return redirect('faculty_register')

        try:
            with transaction.atomic():
                first_name, *last_parts = full_name.split(' ', 1)
                user = User.objects.create_user(
                    username=employee_id,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_parts[0] if last_parts else '',
                    role='FACULTY',
                    mobile=mobile,
                    branch=branch,
                )
                FacultyProfile.objects.create(
                    user=user,
                    employee_id=employee_id,
                    designation=designation,
                )
            messages.success(request, "Faculty account created! Login with your Employee ID.")
            return redirect('login')
        except IntegrityError:
            messages.error(request, "Mobile or Employee ID already exists.")
    return render(request, 'auth/faculty_register.html')


@login_required
def student_dashboard(request):
    if request.user.is_superuser or request.user.role != 'STUDENT':
        return redirect('home')
    if not hasattr(request.user, 'student_profile'):
        logout(request)
        messages.error(request, "Student profile incomplete. Please register again.")
        return redirect('student_register')

    student = request.user.student_profile
    now = datetime.datetime.now()
    today_weekday = now.weekday()

    todays_slots = WeeklyTimetable.objects.filter(
        subject__branch=request.user.branch,
        subject__semester=student.semester,
        day_of_week=today_weekday,
        is_active=True
    )
    active_slots = [slot for slot in todays_slots if is_slot_open_for_attendance(slot, now)]

    subjects = Subject.objects.filter(branch=request.user.branch, semester=student.semester)
    subject_labels = []
    subject_percentages = []
    total_classes_all = 0
    total_present_all = 0

    for sub in subjects:
        total_lectures = Attendance.objects.filter(subject=sub).values('date', 'timetable_slot').distinct().count()
        present_count = Attendance.objects.filter(student=student, subject=sub, is_present=True).count()
        pct = round((present_count / total_lectures) * 100, 1) if total_lectures > 0 else 0.0

        subject_labels.append(sub.code)
        subject_percentages.append(pct)
        total_classes_all += total_lectures
        total_present_all += present_count

    overall_pct = round((total_present_all / total_classes_all) * 100, 1) if total_classes_all > 0 else 0.0
    total_absent_all = max(total_classes_all - total_present_all, 0)

    timetable = WeeklyTimetable.objects.filter(
        subject__branch=request.user.branch,
        subject__semester=student.semester,
        is_active=True
    )
    marks = MidTermMarks.objects.filter(student=student)
    notes = StudyNote.objects.filter(subject__in=subjects).order_by('-uploaded_at')
    notices = Notice.objects.filter(target_semester__isnull=True) | Notice.objects.filter(target_semester=student.semester)

    return render(request, 'student/dashboard.html', {
        'student': student,
        'active_slots': active_slots,
        'window_minutes': ATTENDANCE_WINDOW_MINUTES,
        'overall_pct': overall_pct,
        'total_present': total_present_all,
        'total_absent': total_absent_all,
        'subject_labels_json': json.dumps(subject_labels),
        'subject_pct_json': json.dumps(subject_percentages),
        'timetable': timetable,
        'marks': marks,
        'notes': notes,
        'notices': notices.distinct()[:10],
    })


@login_required
@require_POST
def mark_face_attendance_api(request):
    try:
        if request.user.role != 'STUDENT' or not hasattr(request.user, 'student_profile'):
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

        data = json.loads(request.body)
        slot_id = data.get('slot_id')
        lat = data.get('latitude')
        lon = data.get('longitude')
        face_b64 = data.get('face_image')

        if not all([slot_id, lat, lon, face_b64]):
            return JsonResponse({'status': 'error', 'message': 'Missing GPS location or camera frame.'}, status=400)

        slot = get_object_or_404(WeeklyTimetable, id=slot_id)
        now = datetime.datetime.now()
        if slot.day_of_week != now.weekday() or not is_slot_open_for_attendance(slot, now):
            return JsonResponse({
                'status': 'error',
                'message': f'Attendance window closed! You can only mark attendance within first {ATTENDANCE_WINDOW_MINUTES} mins of lecture start.'
            }, status=400)

        is_inside, distance = verify_campus_geofence(lat, lon)
        if not is_inside:
            allowed = settings.ALLOWED_RADIUS_METERS
            msg = f"Outside GPC Bundi Campus! Distance: {distance}m (Max allowed: {allowed}m)."
            return JsonResponse({'status': 'error', 'message': msg}, status=400)

        student = request.user.student_profile
        is_match, score, err = verify_face_match(student.get_encoding(), face_b64)
        if not is_match:
            return JsonResponse({'status': 'error', 'message': err or 'Face verification failed.'}, status=400)

        today = datetime.date.today()
        if Attendance.objects.filter(student=student, timetable_slot=slot, date=today).exists():
            return JsonResponse({'status': 'error', 'message': 'Attendance record already exists for this lecture today.'}, status=400)

        Attendance.objects.create(
            student=student,
            subject=slot.subject,
            timetable_slot=slot,
            latitude=lat,
            longitude=lon,
            face_match_confidence=score,
        )
        return JsonResponse({'status': 'success', 'message': f'Present marked for {slot.subject.name}! (Match: {int(score*100)}%)'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Server Error: {str(e)}'}, status=500)


@login_required
@require_POST
def re_register_face_api(request):
    try:
        if request.user.role != 'STUDENT' or not hasattr(request.user, 'student_profile'):
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

        data = json.loads(request.body)
        password = data.get('password', '')
        face_b64 = data.get('face_image', '')

        if not password or not face_b64:
            return JsonResponse({'status': 'error', 'message': 'Account password and live camera capture are required.'}, status=400)

        if not request.user.check_password(password):
            return JsonResponse({'status': 'error', 'message': 'Incorrect account password! Face update denied.'}, status=400)

        embedding, err = extract_face_embedding(face_b64)
        if err:
            return JsonResponse({'status': 'error', 'message': f'Face Error: {err}'}, status=400)

        student = request.user.student_profile
        if hasattr(student, 'set_encoding'):
            student.set_encoding(embedding)
        elif hasattr(student, 'face_encoding'):
            student.face_encoding = json.dumps(embedding)
        student.save()

        return JsonResponse({'status': 'success', 'message': 'New Face ID updated successfully! You can now mark attendance with your updated face.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Server Error: {str(e)}'}, status=500)


@login_required
@require_POST
def register_fingerprint_api(request):
    """Student ke profile mein Mantra MFS100 se ISO fingerprint template save karta hai."""
    if request.user.role != 'STUDENT' or not hasattr(request.user, 'student_profile'):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    iso_b64, quality, err = capture_mfs100_fingerprint()
    if err:
        return JsonResponse({'status': 'error', 'message': err}, status=400)

    student = request.user.student_profile
    student.set_fingerprint(iso_b64)
    student.save()
    return JsonResponse({
        'status': 'success',
        'message': f'Mantra MFS100 Fingerprint registered! (Quality: {quality}%)'
    })


@login_required
@require_POST
def mark_fingerprint_attendance_api(request):
    """Mantra MFS100 fingerprint + Campus Geofence se attendance mark karta hai."""
    try:
        if request.user.role != 'STUDENT' or not hasattr(request.user, 'student_profile'):
            return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

        data = json.loads(request.body)
        slot_id = data.get('slot_id')
        lat = data.get('latitude')
        lon = data.get('longitude')

        if not all([slot_id, lat, lon]):
            return JsonResponse({'status': 'error', 'message': 'Lecture slot aur GPS location zaroori hai.'}, status=400)

        slot = get_object_or_404(WeeklyTimetable, id=slot_id)
        now = datetime.datetime.now()
        if slot.day_of_week != now.weekday() or not is_slot_open_for_attendance(slot, now):
            return JsonResponse({
                'status': 'error',
                'message': f'Attendance window closed! Sirf lecture start ke {ATTENDANCE_WINDOW_MINUTES} min ke andar mark kar sakte hain.'
            }, status=400)

        is_inside, distance = verify_campus_geofence(lat, lon)
        if not is_inside:
            return JsonResponse({
                'status': 'error',
                'message': f'Outside GPC Bundi Campus! Distance: {distance}m'
            }, status=400)

        student = request.user.student_profile
        is_match, score, err = verify_mfs100_fingerprint(student.get_fingerprint())
        if not is_match:
            return JsonResponse({'status': 'error', 'message': err}, status=400)

        today = datetime.date.today()
        if Attendance.objects.filter(student=student, timetable_slot=slot, date=today).exists():
            return JsonResponse({'status': 'error', 'message': 'Is lecture ki attendance pehle hi lag chuki hai.'}, status=400)

        Attendance.objects.create(
            student=student,
            subject=slot.subject,
            timetable_slot=slot,
            latitude=lat,
            longitude=lon,
            face_match_confidence=round(min(score / 2000.0, 1.0), 3),
        )
        return JsonResponse({
            'status': 'success',
            'message': f'Biometric Attendance Marked for {slot.subject.name}! (MFS100 Score: {score})'
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Server Error: {str(e)}'}, status=500)


@login_required
def faculty_dashboard(request):
    if request.user.is_superuser or request.user.role == 'HOD':
        return redirect('hod_dashboard')
    if request.user.role != 'FACULTY':
        return redirect('home')
    if not hasattr(request.user, 'faculty_profile'):
        logout(request)
        messages.error(request, "Faculty profile missing. Please register again.")
        return redirect('faculty_register')

    faculty = request.user.faculty_profile
    subjects = Subject.objects.filter(faculty=faculty)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_subject':
            Subject.objects.get_or_create(
                code=request.POST.get('code').strip().upper(),
                defaults={
                    'name': request.POST.get('name').strip(),
                    'branch': request.user.branch,
                    'semester': int(request.POST.get('semester')),
                    'faculty': faculty,
                }
            )
            messages.success(request, "Subject added.")

        elif action == 'add_timetable':
            sub = get_object_or_404(Subject, id=request.POST.get('subject_id'), faculty=faculty)
            WeeklyTimetable.objects.get_or_create(
                subject=sub,
                day_of_week=int(request.POST.get('day_of_week')),
                start_time=request.POST.get('start_time'),
                defaults={
                    'end_time': request.POST.get('end_time'),
                    'room_no': request.POST.get('room_no', '').strip(),
                }
            )
            messages.success(request, "Weekly lecture slot saved! It will repeat automatically every week.")

        elif action == 'delete_timetable':
            slot = get_object_or_404(WeeklyTimetable, id=request.POST.get('slot_id'), subject__faculty=faculty)
            slot.delete()
            messages.success(request, "Lecture slot removed from weekly timetable.")

        elif action == 'toggle_attendance':
            att_record = get_object_or_404(Attendance, id=request.POST.get('attendance_id'), subject__faculty=faculty)
            att_record.is_present = not att_record.is_present
            att_record.save()
            status_label = "PRESENT" if att_record.is_present else "ABSENT (Indiscipline / Override)"
            messages.warning(request, f"{att_record.student.enrollment_id} ({att_record.student.user.get_full_name()}) marked as {status_label} for {att_record.subject.code} ({att_record.date}).")

        elif action == 'upload_note':
            sub = get_object_or_404(Subject, id=request.POST.get('subject_id'), faculty=faculty)
            StudyNote.objects.create(
                subject=sub,
                uploaded_by=faculty,
                title=request.POST.get('title').strip(),
                description=request.POST.get('description', '').strip(),
                file=request.FILES.get('note_file'),
            )
            messages.success(request, "Study note uploaded for students.")

        elif action == 'post_notice':
            Notice.objects.create(
                title=request.POST.get('title').strip(),
                content=request.POST.get('content').strip(),
                category=request.POST.get('category', 'COLLEGE'),
                target_semester=request.POST.get('semester') or None,
                posted_by=request.user,
            )
            messages.success(request, "Notice published.")

        elif action == 'save_marks':
            sub = get_object_or_404(Subject, id=request.POST.get('subject_id'), faculty=faculty)
            student = get_object_or_404(StudentProfile, id=request.POST.get('student_id'))
            mt1_raw = request.POST.get('mid_term_1', '').strip()
            mt2_raw = request.POST.get('mid_term_2', '').strip()

            mark_obj, _ = MidTermMarks.objects.get_or_create(student=student, subject=sub)
            if not mark_obj.is_locked:
                if mt1_raw != '':
                    mark_obj.mid_term_1 = float(mt1_raw)
                if mt2_raw != '':
                    mark_obj.mid_term_2 = float(mt2_raw)
                mark_obj.save()
                messages.success(request, f"Mid-Term marks saved for {student.enrollment_id}.")
            else:
                messages.error(request, "Marks are locked by HOD!")

        return redirect('faculty_dashboard')

    timetable = WeeklyTimetable.objects.filter(subject__in=subjects)
    students = StudentProfile.objects.filter(user__branch=request.user.branch)
    notes = StudyNote.objects.filter(uploaded_by=faculty)
    saved_marks = MidTermMarks.objects.filter(subject__in=subjects).select_related('student', 'subject')
    attendance_logs = Attendance.objects.filter(subject__in=subjects).select_related('student', 'student__user', 'subject', 'timetable_slot').order_by('-date', '-timestamp')

    return render(request, 'faculty/dashboard.html', {
        'faculty': faculty,
        'subjects': subjects,
        'timetable': timetable,
        'students': students,
        'notes': notes,
        'saved_marks': saved_marks,
        'attendance_logs': attendance_logs,
    })


@login_required
def hod_dashboard(request):
    if not (request.user.is_superuser or request.user.role == 'HOD'):
        return redirect('home')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'hod_edit_marks':
            mark_obj = get_object_or_404(MidTermMarks, id=request.POST.get('mark_id'))
            mt1_raw = request.POST.get('mid_term_1', '').strip()
            mt2_raw = request.POST.get('mid_term_2', '').strip()
            mark_obj.mid_term_1 = float(mt1_raw) if mt1_raw != '' else None
            mark_obj.mid_term_2 = float(mt2_raw) if mt2_raw != '' else None
            mark_obj.hod_remarks = request.POST.get('hod_remarks', '').strip()
            mark_obj.updated_by_hod = True
            mark_obj.is_locked = bool(request.POST.get('is_locked'))
            mark_obj.save()
            messages.success(request, f"HOD updated marks for {mark_obj.student.enrollment_id}.")

        elif action == 'hod_notice':
            Notice.objects.create(
                title=request.POST.get('title').strip(),
                content=request.POST.get('content').strip(),
                category=request.POST.get('category', 'BTER'),
                posted_by=request.user,
            )
            messages.success(request, "Official Notice posted.")
        return redirect('hod_dashboard')

    students = StudentProfile.objects.select_related('user').all()
    defaulters = []
    safe_count = 0
    warning_count = 0
    critical_count = 0

    for st in students:
        subs = Subject.objects.filter(branch=st.user.branch, semester=st.semester)
        total_lec = Attendance.objects.filter(subject__in=subs).values('date', 'timetable_slot').distinct().count()
        present_lec = Attendance.objects.filter(student=st, is_present=True).count()
        pct = round((present_lec / total_lec) * 100, 1) if total_lec > 0 else 100.0

        if pct >= 75:
            safe_count += 1
        elif pct >= 65:
            warning_count += 1
            defaulters.append({
                'student': st,
                'pct': pct,
                'parent_whatsapp_url': build_low_attendance_whatsapp_url(st, pct),
                'student_whatsapp_url': build_student_low_attendance_whatsapp_url(st, pct),
            })
        else:
            critical_count += 1
            defaulters.append({
                'student': st,
                'pct': pct,
                'parent_whatsapp_url': build_low_attendance_whatsapp_url(st, pct),
                'student_whatsapp_url': build_student_low_attendance_whatsapp_url(st, pct),
            })

    all_marks = MidTermMarks.objects.select_related('student', 'subject').all()
    notices = Notice.objects.all()[:10]

    return render(request, 'hod/dashboard.html', {
        'total_students': students.count(),
        'total_faculty': FacultyProfile.objects.count(),
        'defaulters': defaulters,
        'all_marks': all_marks,
        'notices': notices,
        'chart_distribution_json': json.dumps([safe_count, warning_count, critical_count]),
    })