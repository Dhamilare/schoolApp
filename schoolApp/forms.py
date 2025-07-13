from django import forms
from .models import * # Imports all models from your models.py
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, Field
from django.forms import BaseFormSet, formset_factory


# Form for creating or editing an Assignment
class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ['title', 'subject', '_class', 'term', 'max_score', 'due_date']
        widgets = {
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-input rounded-md shadow-sm'}),
        }
        labels = {
            '_class': 'Class', # Customize label for '_class' field
        }

    def __init__(self, *args, **kwargs):
        # The 'teacher' instance is passed to limit choices for subjects and classes
        self.teacher = kwargs.pop('teacher', None)
        super().__init__(*args, **kwargs)

        # Crispy Forms Helper for layout and styling
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field('title', css_class='form-control rounded-md shadow-sm'),
            Row(
                Column(Field('subject', css_class='form-select rounded-md shadow-sm'), css_class='col-span-1'),
                Column(Field('_class', css_class='form-select rounded-md shadow-sm'), css_class='col-span-1'),
                css_class='grid grid-cols-1 md:grid-cols-2 gap-4' # Tailwind grid for responsiveness
            ),
            Row(
                Column(Field('term', css_class='form-select rounded-md shadow-sm'), css_class='col-span-1'),
                Column(Field('max_score', css_class='form-input rounded-md shadow-sm'), css_class='col-span-1'),
                css_class='grid grid-cols-1 md:grid-cols-2 gap-4' # Tailwind grid for responsiveness
            ),
            Field('due_date', css_class='form-input rounded-md shadow-sm'),
            Submit('submit', 'Save Assignment', css_class='bg-primary hover:bg-indigo-700 text-white font-bold py-2 px-4 rounded-md shadow-lg transition duration-300')
        )

        if self.teacher:
            # Teachers can only create assignments for subjects they teach
            self.fields['subject'].queryset = self.teacher.subjects_taught.all()
            self.fields['_class'].queryset = Class.objects.all() # Less restrictive for initial setup

            # Set current term as initial choice, if one exists and is marked as current
            current_term = Term.objects.filter(is_current=True).first()
            if current_term:
                self.fields['term'].initial = current_term


class ScoreForm(forms.ModelForm):
    student_name = forms.CharField(
        label="Student Name",
        required=False, # Not strictly required as it's for display
        widget=forms.TextInput(attrs={'readonly': 'readonly', 'class': 'form-input bg-gray-100 cursor-not-allowed rounded-md shadow-sm'})
    )

    class Meta:
        model = Score
        fields = ['id', 'student', 'score_achieved'] # 'id' is needed for updating existing scores
        widgets = {
            'student': forms.HiddenInput(), # Hide student field, use student_name for display
            'score_achieved': forms.NumberInput(attrs={'class': 'form-input rounded-md shadow-sm'})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.student:
            self.fields['student_name'].initial = f"{self.instance.student.first_name} {self.instance.student.last_name}"
        elif 'initial' in kwargs and 'student' in kwargs['initial']:
            student = Student.objects.get(pk=kwargs['initial']['student'])
            self.fields['student_name'].initial = f"{student.first_name} {student.last_name}"

    def clean_score_achieved(self):
        score_achieved = self.cleaned_data['score_achieved']
        assignment = self.cleaned_data.get('assignment')

        if assignment and score_achieved is not None:
            if score_achieved < 0:
                raise forms.ValidationError("Score cannot be negative.")
            if score_achieved > assignment.max_score:
                raise forms.ValidationError(f"Score cannot exceed {assignment.max_score}.")
        return score_achieved



class AttendanceForm(forms.ModelForm):
    student_name = forms.CharField(
        label="Student Name",
        required=False,
        widget=forms.TextInput(attrs={
            'readonly': 'readonly',
            'class': 'form-input mt-1 block w-full bg-gray-100 cursor-not-allowed rounded-md border-gray-300 shadow-sm'
        })
    )

    class Meta:
        model = Attendance
        fields = ['id', 'student', 'status']
        widgets = {
            'student': forms.HiddenInput(),
            'status': forms.Select(attrs={
                'class': 'block w-full px-3 py-2 text-base border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-primary focus:border-primary transition duration-200 ease-in-out'
            })
        }

    def __init__(self, *args, **kwargs):
        self.already_marked = kwargs.pop('already_marked', False)
        student_obj_for_display = kwargs.pop('student_obj_for_display', None)

        super().__init__(*args, **kwargs)

        # Initialize student_name display field
        self.fields['student_name'].initial = ""

        if student_obj_for_display:
            self.fields['student_name'].initial = f"{student_obj_for_display.first_name} {student_obj_for_display.last_name}"
        elif self.instance and self.instance.pk and hasattr(self.instance, 'student') and self.instance.student:
            self.fields['student_name'].initial = f"{self.instance.student.first_name} {self.instance.student.last_name}"
        elif 'initial' in kwargs and 'student' in kwargs['initial']:
            try:
                student = Student.objects.get(pk=kwargs['initial']['student'])
                self.fields['student_name'].initial = f"{student.first_name} {student.last_name}"
            except Student.DoesNotExist:
                self.fields['student_name'].initial = "N/A (Student not found)"

        # Disable the status field if attendance is already marked
        if self.already_marked:
            self.fields['status'].widget.attrs['disabled'] = 'disabled'

    def clean_status(self):
        """
        Preserve the existing status value if the field is disabled.
        """
        if self.already_marked:
            # Return the original value from instance to avoid data loss on disabled field
            return self.instance.status
        else:
            return self.cleaned_data.get('status')


class BaseAttendanceFormSet(BaseFormSet):
    def __init__(self, *args, **kwargs):
        self.selected_class = kwargs.pop('selected_class', None)
        self.attendance_date = kwargs.pop('attendance_date', None)

        # Build a map of students in the selected class for quick lookup
        self.students_in_class_map = {
            s.id: s for s in Student.objects.filter(current_class=self.selected_class).order_by('last_name', 'first_name')
        } if self.selected_class else {}

        super().__init__(*args, **kwargs)

        # Initialize with existing attendance data or defaults if this is NOT a POST submission
        if not kwargs.get('data'):
            initial_data_for_forms = []
            existing_attendance = {
                att.student_id: att
                for att in Attendance.objects.filter(_class=self.selected_class, date=self.attendance_date)
            }

            for student_id, student_obj in self.students_in_class_map.items():
                initial_entry = {
                    'student': student_id,
                    'status': existing_attendance[student_id].status if student_id in existing_attendance else 'P',
                }
                if student_id in existing_attendance:
                    initial_entry['id'] = existing_attendance[student_id].id
                initial_data_for_forms.append(initial_entry)

            self.initial = initial_data_for_forms
            # Removed the line: self.extra = len(initial_data_for_forms)


    def _construct_form(self, i, **kwargs):
        initial = self.initial or []
        form_initial_data = initial[i] if i < len(initial) else {}
        student_id = form_initial_data.get('student')
        attendance_id = form_initial_data.get('id', None)

        student_obj_for_display = self.students_in_class_map.get(student_id) if student_id else None
        already_marked = attendance_id is not None

        kwargs['initial'] = form_initial_data
        kwargs['student_obj_for_display'] = student_obj_for_display
        kwargs['already_marked'] = already_marked

        form = super()._construct_form(i, **kwargs)

        # Allow skipping validation on already marked attendance forms
        if already_marked:
            form.empty_permitted = True

        return form


AttendanceFormSet = formset_factory(
    AttendanceForm,
    formset=BaseAttendanceFormSet,
    extra=0
)

class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name', 'code']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input rounded-md shadow-sm'}),
            'code': forms.TextInput(attrs={'class': 'form-input rounded-md shadow-sm'}),
        }
        labels = {
            'name': 'Subject Name',
            'code': 'Subject Code (Optional)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field('name', css_class='form-control'),
            Field('code', css_class='form-control'),
            Submit('submit', 'Add Subject', css_class='bg-primary hover:bg-indigo-700 text-white font-bold py-2 px-4 rounded-md shadow-lg transition duration-300')
        )
