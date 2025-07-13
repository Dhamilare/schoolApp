# views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.forms import formset_factory
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Count, Avg, Sum
from django.template.loader import render_to_string
import json
import traceback
from weasyprint import HTML, CSS
from .models import *
from .forms import *

# --- Helper functions for Role-Based Access Control (RBAC) ---
def is_teacher(user):
    return user.is_authenticated and user.is_teacher

def is_parent(user):
    return user.is_authenticated and user.is_parent

def is_admin(user):
    return user.is_authenticated and user.is_admin

# --- Existing Views ---
@login_required
def home(request):
    """
    Renders the home page for authenticated users with dashboard data.
    Redirects parents to their specific dashboard.
    """
    if request.user.is_parent:
        return redirect('parent_dashboard')

    context = {
        'page_title': 'Dashboard',
        'user_is_teacher': request.user.is_teacher,
        'user_is_parent': request.user.is_parent,
        'user_is_admin': request.user.is_admin,
        'available_terms': Term.objects.all().order_by('-start_date'),
    }

    context['total_students'] = Student.objects.count()
    context['total_teachers'] = Teacher.objects.count()
    context['total_classes'] = Class.objects.count()
    context['total_subjects'] = Subject.objects.count()

    if request.user.is_teacher:
        teacher_profile = get_object_or_404(Teacher, user=request.user)
        teacher_classes = Class.objects.filter(class_teacher=teacher_profile)
        teacher_subjects = teacher_profile.subjects_taught.all()

        context['teacher_classes'] = teacher_classes
        context['teacher_subjects'] = teacher_subjects
        context['teacher_assignment_count'] = Assignment.objects.filter(recorded_by=request.user).count()

        class_student_counts_data = Class.objects.annotate(student_count=Count('students')).order_by('name')
        context['class_names'] = json.dumps([c.name for c in class_student_counts_data])
        context['class_student_counts'] = json.dumps([c.student_count for c in class_student_counts_data])

    return render(request, 'dashboard.html', context)


# --- NEW: Parent Dashboard View ---
@login_required
@user_passes_test(is_parent)
def parent_dashboard(request):
    """
    Renders the dedicated dashboard for parent users.
    Displays information about their children.
    """
    parent_children = Student.objects.filter(parent=request.user).order_by('current_class__name', 'last_name', 'first_name')
    available_terms = Term.objects.all().order_by('-start_date')

    children_data = []
    for child in parent_children:
        recent_scores = Score.objects.filter(student=child).order_by('-date_recorded')[:5]
        recent_attendance = Attendance.objects.filter(student=child).order_by('-date')[:5]

        current_term = Term.objects.filter(is_current=True).first()
        child_current_term_average = None
        if current_term:
            child_scores_in_current_term = Score.objects.filter(
                student=child,
                assignment__term=current_term
            )
            total_score_achieved = child_scores_in_current_term.aggregate(Sum('score_achieved'))['score_achieved__sum'] or 0
            total_max_score_possible = sum(score.assignment.max_score for score in child_scores_in_current_term)

            if total_max_score_possible > 0:
                child_current_term_average = (total_score_achieved / total_max_score_possible) * 100
                child_current_term_average = round(child_current_term_average, 2)
            else:
                child_current_term_average = 0

        children_data.append({
            'child': child,
            'recent_scores': recent_scores,
            'recent_attendance': recent_attendance,
            'current_term_average': child_current_term_average,
        })

    context = {
        'page_title': 'My Children\'s Dashboard',
        'children_data': children_data,
        'available_terms': available_terms,
        'current_term': current_term,
    }
    return render(request, 'parent/dashboard.html', context)


# --- AJAX endpoint for teacher dashboard chart data ---
@login_required
@user_passes_test(is_teacher)
def teacher_dashboard_data(request):
    teacher_profile = get_object_or_404(Teacher, user=request.user)

    subjects_taught_by_teacher = teacher_profile.subjects_taught.all()
    subject_avg_scores = []
    for subject in subjects_taught_by_teacher:
        avg_score = Score.objects.filter(
            assignment__subject=subject,
            assignment__recorded_by=request.user
        ).aggregate(Avg('score_achieved'))['score_achieved__avg']
        subject_avg_scores.append({
            'subject': subject.name,
            'avg_score': round(avg_score, 2) if avg_score else 0
        })

    today = timezone.localdate()
    attendance_summary = []
    classes_managed = Class.objects.filter(class_teacher=teacher_profile)
    for cls in classes_managed:
        daily_attendance = Attendance.objects.filter(_class=cls, date=today)
        present_count = daily_attendance.filter(status='P').count()
        absent_count = daily_attendance.filter(status='A').count()
        late_count = daily_attendance.filter(status='L').count()
        attendance_summary.append({
            'class_name': cls.name,
            'present': present_count,
            'absent': absent_count,
            'late': late_count,
            'total_students': Student.objects.filter(current_class=cls).count()
        })

    data = {
        'subject_avg_scores': subject_avg_scores,
        'attendance_summary': attendance_summary,
    }
    return JsonResponse(data)


# --- Teacher Grade Management Views ---
@login_required
@user_passes_test(is_teacher)
def assignment_list(request):
    teacher_assignments = Assignment.objects.filter(recorded_by=request.user).order_by('-date_given')
    context = {
        'page_title': 'My Assignments',
        'assignments': teacher_assignments,
    }
    return render(request, 'teacher/assignment_list.html', context)


@login_required
@user_passes_test(is_teacher)
def create_assignment(request):
    teacher_profile = get_object_or_404(Teacher, user=request.user)
    if request.method == 'POST':
        form = AssignmentForm(request.POST, teacher=teacher_profile)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.recorded_by = request.user
            assignment.save()
            messages.success(request, f"Assignment '{assignment.title}' created successfully!")
            return redirect('assignment_list')
    else:
        form = AssignmentForm(teacher=teacher_profile)

    context = {
        'page_title': 'Create New Assignment',
        'form': form,
    }
    return render(request, 'teacher/create_assignment.html', context)


@login_required
@user_passes_test(is_teacher)
def input_scores(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id, recorded_by=request.user)

    print(f"Attempting to input scores for Assignment ID: {assignment_id}")
    print(f"Assignment Title: {assignment.title}")
    print(f"Assignment Class: {assignment._class.name}")

    students_in_class = Student.objects.filter(current_class=assignment._class).order_by('last_name', 'first_name')

    print(f"Students found in class {assignment._class.name}: {students_in_class.count()}")

    initial_scores_data = []
    existing_scores = {score.student_id: score for score in Score.objects.filter(assignment=assignment)}

    for student in students_in_class:
        initial_scores_data.append({
            'id': existing_scores[student.id].id if student.id in existing_scores else '',
            'student': student.id,
            'score_achieved': existing_scores[student.id].score_achieved if student.id in existing_scores else None,
        })

    print(f"Initial scores data prepared: {len(initial_scores_data)} entries")

    ScoreFormSet = formset_factory(
        ScoreForm,
        extra=len(students_in_class),
        can_delete=False
    )

    if request.method == 'POST':
        formset = ScoreFormSet(request.POST, initial=initial_scores_data, prefix='scores')
        print(f"Formset is valid (POST): {formset.is_valid()}")
        if not formset.is_valid():
            for form_err in formset.errors:
                print(f"Formset Error: {form_err}")
            for i, form_obj in enumerate(formset):
                if form_obj.errors:
                    print(f"Form {i} errors: {form_obj.errors}")


        if formset.is_valid():
            with transaction.atomic():
                for form in formset:
                    score_achieved = form.cleaned_data.get('score_achieved')
                    student_id = form.cleaned_data.get('student')
                    score_id = form.cleaned_data.get('id')

                    student_obj = get_object_or_404(Student, pk=student_id)

                    if score_achieved is not None and score_achieved != '':
                        if score_id:
                            score_obj = Score.objects.get(id=score_id)
                            score_obj.score_achieved = score_achieved
                            score_obj.recorded_by = request.user
                            score_obj.save()
                        else:
                            Score.objects.create(
                                assignment=assignment,
                                student=student_obj,
                                score_achieved=score_achieved,
                                recorded_by=request.user
                            )
            messages.success(request, f"Scores for '{assignment.title}' updated successfully!")
            return redirect('input_scores', assignment_id=assignment.id)
        else:
            messages.error(request, "Please correct the errors in the score input.")

    else: # GET request
        formset = ScoreFormSet(initial=initial_scores_data, prefix='scores')
        print(f"Formset has {len(formset.forms)} forms for GET request.")

    for form in formset:
        student_id = form.initial.get('student')
        if student_id:
            try:
                student = Student.objects.get(pk=student_id)
                form.fields['student_name'].initial = f"{student.first_name} {student.last_name}"
            except Student.DoesNotExist:
                form.fields['student_name'].initial = "N/A (Student not found)"
                print(f"WARNING: Student with ID {student_id} not found when populating student_name in form.")
        else:
            form.fields['student_name'].initial = "N/A (No student ID)"
            print(f"WARNING: No student ID found for a form in formset.")


    context = {
        'page_title': f'Input Scores for {assignment.title}',
        'assignment': assignment,
        'formset': formset,
        'students_in_class': students_in_class,
    }
    return render(request, 'teacher/input_scores.html', context)


@login_required
@user_passes_test(is_teacher)
@require_POST
def save_scores_ajax(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id, recorded_by=request.user)
    students_in_class = Student.objects.filter(current_class=assignment._class).order_by('last_name', 'first_name')
    initial_scores_data = []
    existing_scores = {score.student_id: score for score in Score.objects.filter(assignment=assignment)}

    for student in students_in_class:
        initial_scores_data.append({
            'id': existing_scores[student.id].id if student.id in existing_scores else '',
            'student': student.id,
            'score_achieved': existing_scores[student.id].score_achieved if student.id in existing_scores else None,
        })

    ScoreFormSet = formset_factory(
        ScoreForm,
        extra=len(students_in_class),
        can_delete=False
    )

    formset = ScoreFormSet(request.POST, initial=initial_scores_data, prefix='scores')

    if formset.is_valid():
        try:
            with transaction.atomic():
                for form in formset:
                    if form.cleaned_data:
                        score_achieved = form.cleaned_data.get('score_achieved')
                        student_id = form.cleaned_data.get('student')
                        score_id = form.cleaned_data.get('id')

                        student_obj = get_object_or_404(Student, pk=student_id)

                        if score_achieved is not None and score_achieved != '':
                            if score_id:
                                score_obj = Score.objects.get(id=score_id)
                                score_obj.score_achieved = score_achieved
                                score_obj.recorded_by = request.user
                                score_obj.save()
                            else:
                                Score.objects.create(
                                    assignment=assignment,
                                    student=student_obj,
                                    score_achieved=score_achieved,
                                    recorded_by=request.user
                                )
            return JsonResponse({'status': 'success', 'message': 'Scores saved successfully!'})
        except Exception as e:
            traceback.print_exc()
            return JsonResponse({'status': 'error', 'message': f'Database error: {str(e)}'}, status=500)
    else:
        errors = {form.prefix: form.errors for form in formset if form.errors}
        return JsonResponse({'status': 'error', 'message': 'Validation failed', 'errors': errors}, status=400)


# --- Teacher Attendance Management Views ---

@login_required
@user_passes_test(is_teacher)
def select_class_for_attendance(request):
    teacher_profile = get_object_or_404(Teacher, user=request.user)
    available_classes = Class.objects.all().order_by('name')

    context = {
        'page_title': 'Select Class for Attendance',
        'classes': available_classes,
        'today': timezone.localdate().isoformat(),
    }
    return render(request, 'teacher/select_class_for_attendance.html', context)


@login_required
@user_passes_test(is_teacher)
def mark_attendance(request, class_slug, date_str):
    print(f"DEBUG: Entering mark_attendance view for class_slug={class_slug}, date_str={date_str}")

    selected_class = get_object_or_404(Class, slug=class_slug)
    print(f"DEBUG: Found selected_class: {selected_class.name} (ID: {selected_class.id}, Slug: {selected_class.slug})")

    attendance_date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
    print(f"DEBUG: Attendance Date: {attendance_date}")

    AttendanceFormSetInstance = formset_factory(AttendanceForm, formset=BaseAttendanceFormSet, extra=0)

    if request.method == 'POST':
        formset = AttendanceFormSetInstance(
            request.POST,
            selected_class=selected_class,
            attendance_date=attendance_date,
            prefix='attendance'
        )

        if formset.is_valid():
            with transaction.atomic():
                for form in formset:
                    if not form.cleaned_data:
                        continue  # Skip blank form
                    student_id = form.cleaned_data.get('student')
                    status = form.cleaned_data.get('status')
                    student_obj = get_object_or_404(Student, pk=student_id)

                    if form.instance and form.instance.pk:
                        attendance_obj = form.instance
                        attendance_obj.status = status
                        attendance_obj.recorded_by = request.user
                        attendance_obj.save()
                    else:
                        Attendance.objects.create(
                            student=student_obj,
                            date=attendance_date,
                            status=status,
                            _class=selected_class,
                            recorded_by=request.user
                        )
            messages.success(request, f"Attendance for {selected_class.name} on {attendance_date.strftime('%Y-%m-%d')} saved successfully!")
            return redirect('mark_attendance', class_slug=class_slug, date_str=date_str)
        else:
            messages.error(request, "Please correct the errors in the attendance input.")

    else:
        formset = AttendanceFormSetInstance(
            selected_class=selected_class,
            attendance_date=attendance_date,
            prefix='attendance'
        )
        print(f"DEBUG: Formset has {len(formset.forms)} forms for GET request.")

    context = {
        'page_title': f'Mark Attendance for {selected_class.name} on {attendance_date.strftime("%B %d, %Y")}',
        'selected_class': selected_class,
        'attendance_date': attendance_date,
        'formset': formset,
    }
    return render(request, 'teacher/mark_attendance.html', context)


@login_required
@user_passes_test(is_teacher)
@require_POST
def save_attendance_ajax(request, class_slug, date_str):
    selected_class = get_object_or_404(Class, slug=class_slug)
    attendance_date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()

    AttendanceFormSetInstance = formset_factory(AttendanceForm, formset=BaseAttendanceFormSet, extra=0)

    formset = AttendanceFormSetInstance(
        request.POST,
        selected_class=selected_class,
        attendance_date=attendance_date,
        prefix='attendance'
    )

    if formset.is_valid():
        try:
            with transaction.atomic():
                for form in formset:
                    if form.empty_permitted and not form.has_changed():
                        # Skip forms that are allowed to be empty and unchanged (already marked, untouched)
                        continue

                    if not form.cleaned_data:
                        continue  # Skip blank forms

                    student = form.cleaned_data['student']
                    if isinstance(student, int):
                        student = Student.objects.get(pk=student)

                    status = form.cleaned_data['status']

                    if form.instance and form.instance.pk:
                        attendance_obj = form.instance
                        # Only update if status changed
                        if attendance_obj.status != status:
                            attendance_obj.status = status
                            attendance_obj.recorded_by = request.user
                            attendance_obj.save()
                    else:
                        Attendance.objects.create(
                            student=student,
                            date=attendance_date,
                            status=status,
                            _class=selected_class,
                            recorded_by=request.user
                        )

            return JsonResponse({'status': 'success', 'message': 'Attendance saved successfully!'})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({'status': 'error', 'message': f'Database error: {str(e)}'}, status=500)

    else:
        # Debug print each form's errors
        for i, form in enumerate(formset):
            print(f"DEBUG: Form {i} cleaned_data: {form.cleaned_data}")
            print(f"DEBUG: Form {i} errors: {form.errors}")

        errors = {form.prefix: form.errors for form in formset if form.errors}
        return JsonResponse({'status': 'error', 'message': 'Validation failed', 'errors': errors}, status=400)

@login_required
@user_passes_test(is_teacher)
def attendance_history(request):
    teacher_profile = get_object_or_404(Teacher, user=request.user)
    all_attendance_records = Attendance.objects.all().order_by('-date', '_class__name', 'student__last_name')
    context = {
        'page_title': 'Attendance History',
        'attendance_records': all_attendance_records,
    }
    return render(request, 'teacher/attendance_history.html', context)


# --- PDF Report Card Generation View ---
@login_required
@user_passes_test(lambda u: u.is_parent or u.is_teacher or u.is_admin)
def generate_report_card_pdf(request, student_id, term_id):
    student = get_object_or_404(Student, id=student_id)
    term = get_object_or_404(Term, id=term_id)
    school_profile = SchoolProfile.objects.first()

    if request.user.is_parent and student.parent != request.user:
        messages.error(request, "You are not authorized to view this student's report card.")
        return redirect('home')

    scores = Score.objects.filter(
        student=student,
        assignment__term=term
    ).select_related('assignment__subject', 'assignment___class').order_by('assignment__subject__name')

    report_card_data = {}
    total_term_score = 0
    total_max_score_possible = 0
    subjects_graded = set()

    for score in scores:
        subject_name = score.assignment.subject.name
        if subject_name not in report_card_data:
            report_card_data[subject_name] = {
                'scores': [],
                'total_score': 0,
                'total_max_score': 0,
                'average': 0,
            }
        report_card_data[subject_name]['scores'].append(score)
        total_term_score += score.score_achieved
        total_max_score_possible += score.assignment.max_score
        subjects_graded.add(subject_name)

    for subject_name in subjects_graded:
        subject_scores_for_term = scores.filter(assignment__subject__name=subject_name)
        sum_subject_score = subject_scores_for_term.aggregate(Sum('score_achieved'))['score_achieved__sum'] or 0
        sum_subject_max_score = sum(s.assignment.max_score for s in subject_scores_for_term)

        if sum_subject_max_score > 0:
            report_card_data[subject_name]['average'] = (sum_subject_score / sum_subject_max_score) * 100
        else:
            report_card_data[subject_name]['average'] = 0


    overall_average = (total_term_score / total_max_score_possible) * 100 if total_max_score_possible > 0 else 0

    remark = "Good performance."
    if overall_average < 50:
        remark = "Needs significant improvement."
    elif overall_average < 70:
        remark = "Satisfactory performance."

    context = {
        'student': student,
        'term': term,
        'school_profile': school_profile,
        'report_card_data': report_card_data,
        'overall_average': round(overall_average, 2),
        'remark': remark,
        'current_date': timezone.localdate(),
    }

    html_string = render_to_string('report_card_pdf.html', context)

    pdf_file = HTML(string=html_string).write_pdf()

    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Report_Card_{student.first_name}_{student.last_name}_{term.name}.pdf"'
    return response


# --- Subject Management Views ---
@login_required
@user_passes_test(is_teacher) # Only teachers can add subjects
def create_subject(request):
    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            subject = form.save()
            messages.success(request, f"Subject '{subject.name}' added successfully!")
            return redirect('subject_list') # Redirect to subject list after creation
    else:
        form = SubjectForm()

    context = {
        'page_title': 'Add New Subject',
        'form': form,
    }
    return render(request, 'teacher/create_subject.html', context)

@login_required
@user_passes_test(is_teacher) # Only teachers can update subjects
def update_subject(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    if request.method == 'POST':
        form = SubjectForm(request.POST, instance=subject)
        if form.is_valid():
            subject = form.save()
            messages.success(request, f"Subject '{subject.name}' updated successfully!")
            return redirect('subject_list') # Redirect to subject list after update
    else:
        form = SubjectForm(instance=subject)

    context = {
        'page_title': f'Update Subject: {subject.name}',
        'form': form,
        'subject': subject,
    }
    return render(request, 'teacher/update_subject.html', context) # NEW TEMPLATE: update_subject.html

@login_required
@user_passes_test(is_teacher) # Only teachers can delete subjects
@require_POST # Ensure this view only accepts POST requests for security
def delete_subject(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    subject_name = subject.name
    try:
        subject.delete()
        messages.success(request, f"Subject '{subject_name}' deleted successfully!")
    except Exception as e:
        messages.error(request, f"Error deleting subject '{subject_name}': {e}")
    return redirect('subject_list') # Redirect to subject list after deletion

@login_required
@user_passes_test(is_teacher) # Only teachers can view subject list
def subject_list(request):
    subjects = Subject.objects.all().order_by('name')
    context = {
        'page_title': 'Manage Subjects',
        'subjects': subjects,
    }
    return render(request, 'teacher/subject_list.html', context)