from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.text import slugify

# --- Custom User Model ---
class User(AbstractUser):
    is_teacher = models.BooleanField(default=False, help_text="Designates whether this user is a teacher.")
    is_parent = models.BooleanField(default=False, help_text="Designates whether this user is a parent.")
    is_admin = models.BooleanField(default=False, help_text="Designates whether this user is an administrator.")
    is_student = models.BooleanField(default=False, help_text="Designates whether this user is a student.")
    profile_picture = models.ImageField(
        upload_to='profile_pics/',
        blank=True,
        null=True,
        help_text="Upload a profile picture for the user."
    )
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="User's contact phone number."
    )

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users" 
        app_label = 'schoolApp'


    def __str__(self):
        return self.username

# --- School Profile Model ---
class SchoolProfile(models.Model):
    """
    Represents the profile information of the school.
    """
    name = models.CharField(max_length=255, help_text="Name of the school.")
    address = models.TextField(blank=True, help_text="Physical address of the school.")
    phone_number = models.CharField(max_length=20, blank=True, help_text="School's contact phone number.")
    email = models.EmailField(blank=True, help_text="School's official email address.")
    motto = models.CharField(max_length=255, blank=True, help_text="School motto or slogan.")
    logo = models.ImageField(
        upload_to='school_logos/',
        blank=True,
        null=True,
        help_text="Upload the school logo."
    )

    class Meta:
        verbose_name = "School Profile"
        verbose_name_plural = "School Profiles" # <<< FIXED
        app_label = 'schoolApp'

    def __str__(self):
        return self.name

# --- Subject Model ---
class Subject(models.Model):
    """
    Represents an academic subject taught in the school.
    """
    name = models.CharField(max_length=100, unique=True, help_text="Name of the subject (e.g., Mathematics, English).")
    code = models.CharField(max_length=10, unique=True, blank=True, null=True, help_text="Optional short code for the subject.")
    slug = models.SlugField(max_length=100, unique=True, blank=True, null=True,
                            help_text="A unique slug for the subject, auto-generated from the name.")

    class Meta:
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"
        ordering = ['name']
        app_label = 'schoolApp'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug or (self.pk and self.slug == slugify(self.__class__.objects.get(pk=self.pk).name) and self.name != self.__class__.objects.get(pk=self.pk).name):
            base_slug = slugify(self.name)
            unique_slug = base_slug
            num = 1
            while Subject.objects.filter(slug=unique_slug).exclude(pk=self.pk).exists():
                unique_slug = f"{base_slug}-{num}"
                num += 1
            self.slug = unique_slug
        super().save(*args, **kwargs)


# --- Class Model ---
class Class(models.Model):
    """
    Represents a specific class or grade level (e.g., 'SS1 A', 'JSS3 B').
    """
    name = models.CharField(max_length=100, unique=True, help_text="Name of the class (e.g., Grade 10A, JSS3).")
    slug = models.SlugField(max_length=100, unique=True, blank=True, null=True,
                            help_text="A unique slug for the class, auto-generated from the name.")
    class_teacher = models.OneToOneField(
        'Teacher',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_class',
        help_text="The teacher assigned as the class teacher for this class."
    )

    class Meta:
        verbose_name = "Class"
        verbose_name_plural = "Classes"
        ordering = ['name']
        app_label = 'schoolApp'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug or (self.pk and self.slug == slugify(self.__class__.objects.get(pk=self.pk).name) and self.name != self.__class__.objects.get(pk=self.pk).name):
            base_slug = slugify(self.name)
            unique_slug = base_slug
            num = 1
            while Class.objects.filter(slug=unique_slug).exclude(pk=self.pk).exists():
                unique_slug = f"{base_slug}-{num}"
                num += 1
            self.slug = unique_slug
        super().save(*args, **kwargs)


# --- Teacher Model ---
class Teacher(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={'is_teacher': True},
        help_text="The user account for this teacher."
    )
    staff_id = models.CharField(max_length=50, unique=True, blank=True, null=True, help_text="Unique staff identification number.")
    subjects_taught = models.ManyToManyField(
        Subject,
        blank=True,
        related_name='teachers',
        help_text="Subjects this teacher is qualified to teach."
    )
    date_employed = models.DateField(blank=True, null=True, help_text="Date the teacher was employed.")

    class Meta:
        verbose_name = "Teacher"
        verbose_name_plural = "Teachers" # <<< FIXED
        ordering = ['user__last_name', 'user__first_name']
        app_label = 'schoolApp'

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name}" if self.user.first_name and self.user.last_name else self.user.username


# --- Student Model ---
class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True, related_name='student_profile')
    first_name = models.CharField(max_length=100, help_text="Student's first name.")
    last_name = models.CharField(max_length=100, help_text="Student's last name.")
    student_id = models.CharField(max_length=50, unique=True, blank=True, null=True, help_text="Unique student identification number.")
    date_of_birth = models.DateField(help_text="Student's date of birth.")
    current_class = models.ForeignKey(
        Class,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students',
        help_text="The current class the student is enrolled in."
    )
    parent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children',
        limit_choices_to={'is_parent': True},
        help_text="The parent associated with this student's account."
    )
    gender = models.CharField(
        max_length=10,
        choices=[('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')],
        default='Male',
        help_text="Student's gender."
    )
    admission_date = models.DateField(auto_now_add=True, help_text="Date the student was admitted to the school.")

    class Meta:
        verbose_name = "Student"
        verbose_name_plural = "Students" 
        unique_together = ('first_name', 'last_name', 'date_of_birth')
        ordering = ['current_class__name', 'last_name', 'first_name']
        app_label = 'schoolApp'

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.current_class.name if self.current_class else 'Unassigned'})"

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

# --- Grade Management Models ---

class Term(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="Name of the term (e.g., 'First Term', '2024/2025 Academic Session').")
    start_date = models.DateField(help_text="Start date of the term.")
    end_date = models.DateField(help_text="End date of the term.")
    is_current = models.BooleanField(default=False, help_text="Designates if this is the currently active term.")

    class Meta:
        verbose_name = "Academic Term"
        verbose_name_plural = "Academic Terms" # <<< FIXED
        ordering = ['-start_date']
        app_label = 'schoolApp'

    def __str__(self):
        return self.name

class Assignment(models.Model):
    """
    Represents an assignment, test, or exam for a specific subject and class.
    """
    title = models.CharField(max_length=255, help_text="Title of the assignment or exam (e.g., 'Mid-term Test', 'Homework 1').")
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='assignments',
        help_text="The subject this assignment belongs to."
    )
    _class = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name='assignments',
        help_text="The class for which this assignment is given."
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name='assignments',
        help_text="The academic term this assignment falls under."
    )
    max_score = models.PositiveIntegerField(
        default=100,
        help_text="Maximum possible score for this assignment."
    )
    date_given = models.DateField(
        auto_now_add=True,
        help_text="Date the assignment was created/given."
    )
    due_date = models.DateField(
        blank=True,
        null=True,
        help_text="Optional due date for the assignment."
    )
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'is_teacher': True},
        help_text="The teacher who recorded this assignment."
    )

    class Meta:
        verbose_name = "Assignment/Exam"
        verbose_name_plural = "Assignments/Exams" # <<< FIXED
        unique_together = ('title', 'subject', '_class', 'term')
        ordering = ['-date_given', 'title']
        app_label = 'schoolApp'

    def __str__(self):
        return f"{self.title} - {self.subject.name} ({self._class.name}) - {self.term.name}"

    @property
    def class_obj(self):
        return self._class


class Score(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='scores',
        help_text="The student who received this score."
    )
    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name='scores',
        help_text="The assignment for which this score is recorded."
    )
    score_achieved = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="The score obtained by the student."
    )
    date_recorded = models.DateTimeField(
        auto_now_add=True,
        help_text="Date and time when the score was recorded."
    )
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'is_teacher': True},
        help_text="The teacher who recorded this score."
    )

    class Meta:
        verbose_name = "Score"
        verbose_name_plural = "Scores" # <<< FIXED
        unique_together = ('student', 'assignment')
        ordering = ['assignment__term__start_date', 'assignment__subject__name', 'student__last_name']
        app_label = 'schoolApp'

    def __str__(self):
        return f"{self.student.first_name} {self.student.last_name} - {self.assignment.title}: {self.score_achieved}"


# --- Attendance Module Models ---

class Attendance(models.Model):
    ATTENDANCE_STATUS_CHOICES = [
        ('P', 'Present'),
        ('A', 'Absent'),
        ('L', 'Late'),
        ('E', 'Excused'),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='attendances',
        help_text="The student whose attendance is being recorded."
    )
    date = models.DateField(
        help_text="The date for which attendance is recorded."
    )
    status = models.CharField(
        max_length=1,
        choices=ATTENDANCE_STATUS_CHOICES,
        default='P',
        help_text="Attendance status (Present, Absent, Late, Excused)."
    )
    _class = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name='class_attendances',
        help_text="The class for which this attendance is recorded."
    )
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={'is_teacher': True},
        help_text="The teacher who recorded this attendance."
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        help_text="Date and time when the attendance record was created/last updated."
    )

    class Meta:
        verbose_name = "Attendance"
        verbose_name_plural = "Attendance Records" # <<< FIXED
        unique_together = ('student', 'date', '_class')
        ordering = ['-date', '_class__name', 'student__last_name']
        app_label = 'schoolApp'

    def __str__(self):
        return f"{self.student.first_name} {self.student.last_name} - {self.date} ({self.get_status_display()})"

    @property
    def class_obj(self):
        return self._class
    
    @property 
    def class_name_display(self):
        return self._class.name if self._class else "N/A"
    

class Submission(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='submissions')
    submission_text = models.TextField(blank=True, null=True) # For text-based answers
    submission_file = models.FileField(upload_to='assignment_submissions/', blank=True, null=True) # For file uploads
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_graded = models.BooleanField(default=False)

    class Meta:
        unique_together = ('assignment', 'student') # A student can only submit once per assignment
        ordering = ['-submitted_at']
        verbose_name_plural = "Submissions"

    def __str__(self):
        return f"Submission by {self.student.get_full_name()} for {self.assignment.title}"
