# views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.forms import formset_factory
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Count, Avg, Sum, F
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

def is_student(user):
    return user.is_authenticated and user.is_student


@login_required
def home(request):
    if request.user.is_parent:
        return redirect('parent_dashboard')
    
    if request.user.is_student:
        return redirect('student_dashboard')

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
    teacher_assignments = Assignment.objects.filter(recorded_by=request.user).annotate(
        submission_count=Count('submissions')
    ).order_by('-date_given')
    
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

            if assignment.assignment_type == 'mcq':
                return redirect('create_mcq_questions', assignment_id=assignment.id)
            else:
                return redirect('assignment_list')
    else:
        form = AssignmentForm(teacher=teacher_profile)

    return render(request, 'teacher/create_assignment.html', {
        'page_title': 'Create New Assignment',
        'form': form,
    })


@login_required
@user_passes_test(is_teacher)
def update_assignment(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id, recorded_by=request.user)
    teacher_profile = get_object_or_404(Teacher, user=request.user)

    if request.method == 'POST':
        form = AssignmentForm(request.POST, instance=assignment, teacher=teacher_profile)
        if form.is_valid():
            assignment = form.save()
            messages.success(request, f"Assignment '{assignment.title}' updated successfully!")
            return redirect('assignment_list')
        else:
            messages.error(request, "There was an error updating the assignment. Please correct the form.")
    else:
        form = AssignmentForm(instance=assignment, teacher=teacher_profile)

    context = {
        'page_title': f'Update Assignment: {assignment.title}',
        'assignment': assignment,
        'form': form,
    }
    return render(request, 'teacher/update_assignment.html', context)


@login_required
@user_passes_test(is_teacher)
@require_POST
def delete_assignment(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id, recorded_by=request.user)
    assignment_title = assignment.title
    try:
        assignment.delete()
        messages.success(request, f"Assignment '{assignment_title}' deleted successfully!")
    except Exception as e:
        messages.error(request, f"Error deleting assignment '{assignment_title}': {e}")
    return redirect('assignment_list')


@login_required
@user_passes_test(is_teacher)
def assignment_submissions(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id, recorded_by=request.user)
    submissions = Submission.objects.filter(assignment=assignment).order_by('-submitted_at')

    context = {
        'page_title': f'Submissions for: {assignment.title}',
        'assignment': assignment,
        'submissions': submissions,
    }
    return render(request, 'teacher/assignment_submissions.html', context)


@login_required
@user_passes_test(is_teacher)
def submission_detail(request, submission_id):
    submission = get_object_or_404(Submission, id=submission_id)
    # Ensure the teacher viewing this submission is authorized (e.g., created the assignment)
    if submission.assignment.recorded_by != request.user:
        messages.error(request, "You are not authorized to view this submission.")
        return redirect('assignment_list')

    student_answers = None
    total_score_achieved = None

    if submission.assignment.assignment_type == 'mcq':
        student_answers = StudentAnswer.objects.filter(submission=submission).select_related('question', 'chosen_choice').order_by('question__id')
        # Calculate total score achieved for this MCQ submission
        total_score_achieved = sum(sa.points_awarded for sa in student_answers)

    context = {
        'page_title': f'Submission Detail for {submission.student.get_full_name()}',
        'submission': submission,
        'student_answers': student_answers, # Will be None if not an MCQ
        'total_score_achieved': total_score_achieved, # Will be None if not an MCQ
    }
    return render(request, 'teacher/submission_detail.html', context)


@login_required
@user_passes_test(is_teacher)
def create_mcq_questions(request, assignment_id):
    assignment = get_object_or_404(
        Assignment,
        id=assignment_id,
        recorded_by=request.user,
        assignment_type='mcq'
    )

    questions = list(
        Question.objects.filter(assignment=assignment)
        .prefetch_related('choices')
        .order_by('id')
    )

    QuestionFormSet = formset_factory(QuestionForm, extra=1, can_delete=True)

    if request.method == 'POST':
        question_formset = QuestionFormSet(request.POST, prefix='questions')

        # Attach all ChoiceFormSets BEFORE calling .is_valid()
        for form_index, question_form in enumerate(question_formset.forms):
            choice_prefix = f'choices-{form_index}'
            question_form.choice_formset = ChoiceFormSet(request.POST, prefix=choice_prefix)

        # Now validate
        if question_formset.is_valid() and all(qf.choice_formset.is_valid() for qf in question_formset):
            try:
                with transaction.atomic():
                    total_score = 0.0

                    for form_index, question_form in enumerate(question_formset):
                        if question_form.cleaned_data.get('DELETE', False):
                            if form_index < len(questions):
                                questions[form_index].delete()
                            continue

                        question = question_form.save(commit=False)
                        question.assignment = assignment
                        question.save()

                        correct_choices = 0
                        for choice_form in question_form.choice_formset:
                            if choice_form.cleaned_data and not choice_form.cleaned_data.get('DELETE', False):
                                choice = choice_form.save(commit=False)
                                choice.question = question
                                choice.save()
                                if choice.is_correct:
                                    correct_choices += 1

                        if correct_choices != 1:
                            raise ValidationError("You must select exactly one correct answer.")

                        total_score += float(question.points)

                    assignment.max_score = total_score
                    assignment.save()

                    messages.success(request, f"Questions for '{assignment.title}' saved successfully!")
                    return redirect('create_mcq_questions', assignment_id=assignment.id)

            except Exception as e:
                traceback.print_exc()
                messages.error(request, f"An error occurred: {e}")
        else:
            messages.error(request, "Please correct the errors in the forms.")

    else:
        new_form_index = request.GET.get('new_form_index')
        if new_form_index is not None:
            # AJAX request for dynamic form addition
            new_form_index = int(new_form_index)
            question_form = QuestionForm(prefix=f'questions-{new_form_index}')
            question_form.choice_formset = ChoiceFormSet(prefix=f'choices-{new_form_index}', queryset=Choice.objects.none())

            return render(request, 'teacher/includes/single_question_form.html', {
                'question_form': question_form,
                'form_index': new_form_index,
            })

        # GET request: show all existing questions
        initial_data = [{'question_text': q.question_text, 'points': q.points} for q in questions]
        question_formset = QuestionFormSet(initial=initial_data, prefix='questions')

        for form_index, question_form in enumerate(question_formset.forms):
            if form_index < len(questions):
                question_form.instance = questions[form_index]
                question_form.choice_formset = ChoiceFormSet(
                    queryset=questions[form_index].choices.all(),
                    prefix=f'choices-{form_index}'
                )
            else:
                question_form.choice_formset = ChoiceFormSet(
                    queryset=Choice.objects.none(),
                    prefix=f'choices-{form_index}'
                )

    context = {
        'assignment': assignment,
        'question_formset': question_formset,
    }

    return render(request, 'teacher/create_mcq_questions.html', context)


@login_required
@user_passes_test(is_teacher)
def input_scores(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id, recorded_by=request.user)
    students_in_class = Student.objects.filter(current_class=assignment._class).order_by('last_name', 'first_name')
    existing_scores = {s.student_id: s for s in Score.objects.filter(assignment=assignment)}
    existing_submissions = {s.student_id: s for s in Submission.objects.filter(assignment=assignment)}

    initial_data = [
        {
            'id': existing_scores.get(s.id).id if s.id in existing_scores else '',
            'student': s.id,
            'score_achieved': existing_scores.get(s.id).score_achieved if s.id in existing_scores else None
        }
        for s in students_in_class
    ]

    ScoreFormSet = formset_factory(ScoreForm, extra=len(students_in_class), can_delete=False)

    if request.method == 'POST':
        formset = ScoreFormSet(request.POST, initial=initial_data, prefix='scores')

        if assignment.assignment_type == 'mcq':
            messages.error(request, "Scores for MCQ assignments are automatically calculated and cannot be manually edited here.")
            return redirect('input_scores', assignment_id=assignment.id)

        if formset.is_valid():
            with transaction.atomic():
                for form in formset:
                    score = form.cleaned_data.get('score_achieved')
                    student_id = form.cleaned_data.get('student')
                    score_id = form.cleaned_data.get('id')
                    student = get_object_or_404(Student, pk=student_id)

                    if score is not None and score != '':
                        if score_id:
                            s = Score.objects.get(id=score_id)
                            s.score_achieved = score
                            s.recorded_by = request.user
                            s.save()
                        else:
                            Score.objects.create(
                                assignment=assignment,
                                student=student,
                                score_achieved=score,
                                recorded_by=request.user
                            )
            messages.success(request, f"Scores for '{assignment.title}' updated successfully!")
            return redirect('input_scores', assignment_id=assignment.id)
        else:
            messages.error(request, "Please correct the errors in the score input.")
    else:
        formset = ScoreFormSet(initial=initial_data, prefix='scores')

    for form in formset:
        student_id = form.initial.get('student')
        if student_id:
            student = get_object_or_404(Student, pk=student_id)
            form.fields['student_name'].initial = f"{student.first_name} {student.last_name}"
            form.submission = existing_submissions.get(student_id)
            if assignment.assignment_type == 'mcq':
                form.fields['score_achieved'].widget.attrs['readonly'] = True
                form.fields['score_achieved'].widget.attrs['class'] += ' bg-gray-100 cursor-not-allowed'

    return render(request, 'teacher/input_scores.html', {
        'page_title': f'Input Scores for {assignment.title}',
        'assignment': assignment,
        'formset': formset,
        'students_in_class': students_in_class,
    })


@login_required
@user_passes_test(is_teacher)
@require_POST
def save_scores_ajax(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id, recorded_by=request.user)
    
    if assignment.assignment_type == 'mcq':
        return JsonResponse({'status': 'error', 'message': 'MCQ assignment scores are graded automatically and cannot be manually edited.'}, status=400)

    try:
        data = json.loads(request.body)
        student_id = data.get('student_id')
        score_achieved = data.get('score_achieved')
        
        if student_id is None or score_achieved is None:
            return JsonResponse({'status': 'error', 'message': 'Missing student_id or score_achieved.'}, status=400)

        try:
            score_achieved = float(score_achieved)
        except ValueError:
            return JsonResponse({'status': 'error', 'message': 'Invalid score format. Must be a number.'}, status=400)

        student_obj = get_object_or_404(Student, pk=student_id)

        existing_submission = Submission.objects.filter(assignment=assignment, student=student_obj).first()
        if existing_submission and existing_submission.is_graded:
            return JsonResponse({'status': 'error', 'message': f"Submission for {student_obj.get_full_name()} is already graded and cannot be changed."}, status=400)

        if score_achieved < 0:
            return JsonResponse({'status': 'error', 'message': "Score cannot be negative."}, status=400)
        if score_achieved > float(assignment.max_score):
            return JsonResponse({'status': 'error', 'message': f"Score cannot exceed the assignment's maximum score of {assignment.max_score}."}, status=400)

        Score.objects.update_or_create(
            assignment=assignment,
            student=student_obj,
            defaults={
                'score_achieved': score_achieved,
                'recorded_by': request.user
            }
        )
        if existing_submission:
            existing_submission.is_graded = True
            existing_submission.save()

        return JsonResponse({'status': 'success', 'message': 'Score saved successfully!'})
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON format in request body.'}, status=400)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'status': 'error', 'message': f"An unexpected error occurred: {str(e)}"}, status=500)


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


# --- NEW: Student Dashboard View ---
@login_required
@user_passes_test(is_student)
def student_dashboard(request):
    student_profile = get_object_or_404(Student, user=request.user)
    current_term = Term.objects.filter(is_current=True).first()

    # Assignments for the student's current class and current term
    assigned_assignments = Assignment.objects.filter(
        _class=student_profile.current_class,
        term=current_term
    ).order_by('-due_date')

    # Fetch existing scores for these assignments
    existing_scores = {
        score.assignment_id: score
        for score in Score.objects.filter(student=student_profile, assignment__in=assigned_assignments)
    }

    # Fetch existing submissions for these assignments
    existing_submissions = {
        submission.assignment_id: submission
        for submission in Submission.objects.filter(student=student_profile, assignment__in=assigned_assignments)
    }

    # Prepare assignments data for display
    assignments_data = []
    for assignment in assigned_assignments:
        score = existing_scores.get(assignment.id)
        submission = existing_submissions.get(assignment.id)
        assignments_data.append({
            'assignment': assignment,
            'score': score,
            'submission': submission,
            'is_submitted': submission is not None,
            'is_graded': score is not None and score.score_achieved is not None,
            'is_overdue': assignment.due_date < timezone.localdate() and not submission,
        })

    # Recent attendance for the student
    recent_attendance = Attendance.objects.filter(student=student_profile).order_by('-date')[:7] # Last 7 days

    # Calculate overall average for current term
    overall_average = None
    if current_term:
        student_scores_in_current_term = Score.objects.filter(
            student=student_profile,
            assignment__term=current_term
        )
        total_score_achieved = student_scores_in_current_term.aggregate(Sum('score_achieved'))['score_achieved__sum'] or 0
        total_max_score_possible = sum(score.assignment.max_score for score in student_scores_in_current_term)

        if total_max_score_possible > 0:
            overall_average = (total_score_achieved / total_max_score_possible) * 100
            overall_average = round(overall_average, 2)
        else:
            overall_average = 0

    context = {
        'page_title': f'Student Dashboard - {student_profile.get_full_name()}',
        'student_profile': student_profile,
        'current_term': current_term,
        'assignments_data': assignments_data,
        'recent_attendance': recent_attendance,
        'overall_average': overall_average,
    }
    return render(request, 'student/dashboard.html', context)


@login_required
@user_passes_test(is_student)
def submit_assignment(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id)
    student_profile = get_object_or_404(Student, user=request.user)

    # Ensure the assignment is for this student's class
    if assignment._class != student_profile.current_class:
        messages.error(request, "This assignment is not for your class.")
        return redirect('student_dashboard')

    # Check if a submission already exists for this assignment and student
    existing_submission = Submission.objects.filter(assignment=assignment, student=student_profile).first()

    # Determine if the submission is graded
    is_graded = existing_submission and existing_submission.is_graded

    if assignment.assignment_type == 'text_file':
        if request.method == 'POST':
            if is_graded:
                messages.error(request, "This assignment has already been graded and cannot be re-submitted.")
                return redirect('submit_assignment', assignment_id=assignment.id)

            form = SubmissionForm(request.POST, request.FILES, instance=existing_submission)
            if form.is_valid():
                submission = form.save(commit=False)
                submission.assignment = assignment
                submission.student = student_profile
                submission.is_graded = False # Manual grading for text/file submissions
                submission.save()
                messages.success(request, f"Your submission for '{assignment.title}' has been saved!")
                return redirect('student_dashboard')
            else:
                messages.error(request, "There was an error with your submission. Please correct it.")
        else:
            form = SubmissionForm(instance=existing_submission)
            # If graded, make form fields read-only on GET request
            if is_graded:
                for field_name, field in form.fields.items():
                    field.widget.attrs['readonly'] = 'readonly'
                    field.widget.attrs['disabled'] = 'disabled' # Disable for file input
                    if 'class' in field.widget.attrs:
                        field.widget.attrs['class'] += ' bg-gray-100 cursor-not-allowed'
                    else:
                        field.widget.attrs['class'] = 'bg-gray-100 cursor-not-allowed'


        context = {
            'page_title': f'Submit: {assignment.title}',
            'assignment': assignment,
            'form': form,
            'existing_submission': existing_submission,
            'assignment_type': 'text_file',
            'is_graded_for_text_file': is_graded, # Pass graded status to template
        }
        return render(request, 'student/submit_assignment.html', context)

    elif assignment.assignment_type == 'mcq':
        questions = Question.objects.filter(assignment=assignment).prefetch_related('choices').order_by('id')

        # If no questions are set up for this MCQ, inform the student
        if not questions.exists():
            messages.info(request, "This MCQ assignment has no questions set up yet. Please check back later.")
            return redirect('student_dashboard')

        # If a submission already exists, fetch the student's previous answers
        initial_student_answers = []
        if existing_submission:
            student_answers_map = {sa.question_id: sa for sa in StudentAnswer.objects.filter(submission=existing_submission)}
            for question in questions:
                # Pre-populate with existing answer if available
                initial_student_answers.append({
                    'question': question.id,
                    'chosen_choice': student_answers_map.get(question.id, {}).chosen_choice.id if question.id in student_answers_map and student_answers_map[question.id].chosen_choice else None,
                    'id': student_answers_map.get(question.id, {}).id if question.id in student_answers_map else None,
                })

        StudentAnswerFormSet_instance = formset_factory(
            StudentAnswerForm,
            formset=BaseStudentAnswerFormSet, # Use BaseStudentAnswerFormSet
            extra=0,
            max_num=len(questions),
            validate_max=True
        )

        if request.method == 'POST':
            if is_graded:
                messages.error(request, "This assignment has already been graded and cannot be re-submitted.")
                return redirect('submit_assignment', assignment_id=assignment.id)

            # Pass request.POST and existing submission for proper formset handling
            formset = StudentAnswerFormSet_instance(
                request.POST,
                questions=questions,
                student_submission=existing_submission,
                prefix='mcq_answers'
            )

            if formset.is_valid():
                with transaction.atomic():
                    # Create or update the main Submission object
                    if not existing_submission:
                        submission = Submission.objects.create(
                            assignment=assignment,
                            student=student_profile,
                            submission_text="MCQ Submission", # Placeholder text
                            is_graded=True # Will be graded automatically
                        )
                    else:
                        submission = existing_submission
                        submission.is_graded = True # Mark as graded after re-submission
                        submission.save()

                    total_score_achieved = 0.0
                    for form in formset:
                        question_id = form.cleaned_data['question']
                        chosen_choice = form.cleaned_data.get('chosen_choice') # Can be None if not answered

                        question_obj = get_object_or_404(Question, pk=question_id)
                        is_correct = False
                        points_awarded = 0.0

                        if chosen_choice and chosen_choice.is_correct:
                            is_correct = True
                            points_awarded = question_obj.points
                        total_score_achieved += points_awarded

                        # Create or update StudentAnswer
                        if form.instance.pk: # Existing answer
                            student_answer = form.instance
                            student_answer.chosen_choice = chosen_choice
                            student_answer.is_correct = is_correct
                            student_answer.points_awarded = points_awarded
                            student_answer.save()
                        else: # New answer
                            StudentAnswer.objects.create(
                                submission=submission,
                                question=question_obj,
                                chosen_choice=chosen_choice,
                                is_correct=is_correct,
                                points_awarded=points_awarded
                            )

                    # Update the student's overall score for this assignment
                    # Find or create the Score object
                    score_obj, created = Score.objects.update_or_create(
                        assignment=assignment,
                        student=student_profile,
                        defaults={
                            'score_achieved': total_score_achieved,
                            'recorded_by': request.user # Teacher user will be the grader (or an admin user)
                        }
                    )
                    messages.success(request, f"Your MCQ submission for '{assignment.title}' has been graded!")
                    return redirect('student_dashboard')
            else:
                messages.error(request, "There was an error with your submission. Please correct it.")
        else: # GET request
            formset = StudentAnswerFormSet_instance(
                questions=questions,
                student_submission=existing_submission,
                prefix='mcq_answers',
                initial=initial_student_answers # Pass initial data for pre-filling
            )
            if is_graded:
                for form in formset:
                    form.fields['chosen_choice'].widget.attrs['disabled'] = 'disabled'
                    form.fields['chosen_choice'].widget.attrs['class'] += ' cursor-not-allowed'


        context = {
            'page_title': f'Attempt MCQ: {assignment.title}',
            'assignment': assignment,
            'formset': formset,
            'questions': questions, # Pass questions directly for template display
            'existing_submission': existing_submission,
            'assignment_type': 'mcq',
            'is_graded_for_mcq': is_graded, # Pass graded status to template
        }
        return render(request, 'student/submit_assignment.html', context) # Still use submit_assignment.html, but it will include mcq_submission_form.html
    else:
        messages.error(request, "Invalid assignment type.")
        return redirect('student_dashboard')


@login_required
@user_passes_test(is_teacher)
def create_student(request):
    if request.method == 'POST':
        form = StudentUserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Student account created successfully.")
            return redirect('student_list')
        else:
            messages.error(request, "There was an error creating the student.")
    else:
        form = StudentUserCreationForm()

    return render(request, 'teacher/create_student.html', {
        'form': form,
        'page_title': "Create Student",
    })

@login_required
@user_passes_test(is_teacher) 
def student_list(request):
    students = Student.objects.all().order_by('current_class__name', 'last_name', 'first_name')
    context = {
        'page_title': 'Manage Students',
        'students': students,
    }
    return render(request, 'teacher/student_list.html', context)


@login_required
@user_passes_test(is_teacher)
def update_student(request, pk):
    student = get_object_or_404(Student, pk=pk)
    user = student.user

    if request.method == 'POST':
        form = StudentUserUpdateForm(request.POST, instance=student, user_instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Student '{student.get_full_name()}' updated successfully.")
            return redirect('student_list')
        else:
            messages.error(request, "There was an error updating the student.")
    else:
        form = StudentUserUpdateForm(instance=student, user_instance=user)

    return render(request, 'teacher/update_student.html', {
        'form': form,
        'student': student,
        'page_title': f"Update Student: {student.get_full_name()}",
    })

@login_required
@user_passes_test(is_teacher)
@require_POST 
def delete_student(request, pk): 
    student = get_object_or_404(Student, pk=pk)
    student_name = student.get_full_name()
    try:
        if student.user:
            student.user.delete()
        else:
            student.delete()
        messages.success(request, f"Student '{student_name}' and associated account deleted successfully!")
    except Exception as e:
        messages.error(request, f"Error deleting student '{student_name}': {e}")
    return redirect('student_list')


