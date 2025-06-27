from django import forms
from .models import *
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, Field


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
        widget=forms.TextInput(attrs={'readonly': 'readonly', 'class': 'form-input bg-gray-100 cursor-not-allowed rounded-md shadow-sm'})
    )

    class Meta:
        model = Attendance
        fields = ['id', 'student', 'status'] # 'id' for existing records
        widgets = {
            'student': forms.HiddenInput(), # Hide student field, use student_name for display
            'status': forms.Select(attrs={'class': 'form-select rounded-md shadow-sm'})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.student:
            self.fields['student_name'].initial = f"{self.instance.student.first_name} {self.instance.student.last_name}"
        elif 'initial' in kwargs and 'student' in kwargs['initial']:
            student = Student.objects.get(pk=kwargs['initial']['student'])
            self.fields['student_name'].initial = f"{student.first_name} {student.last_name}"


