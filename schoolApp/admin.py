from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, SchoolProfile, Subject, Class, Teacher, Student, Term, Assignment, Score, Attendance

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        (('Custom Fields'), {'fields': ('is_teacher', 'is_parent', 'is_admin', 'profile_picture', 'phone_number')}),
    )
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_teacher', 'is_parent', 'is_admin', 'is_staff')
    list_filter = ('is_teacher', 'is_parent', 'is_admin', 'is_staff', 'is_superuser')
    search_fields = ('username', 'first_name', 'last_name', 'email')


@admin.register(SchoolProfile)
class SchoolProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone_number')
    search_fields = ('name', 'email')


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'slug',) # Added slug
    search_fields = ('name', 'code',)
    prepopulated_fields = {'slug': ('name',)} # <<< NEW: Auto-populate slug from name


@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'class_teacher')
    list_filter = ('class_teacher',)
    search_fields = ('name', 'slug',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('user_username', 'user_full_name', 'staff_id', 'date_employed')
    def user_username(self, obj):
        return obj.user.username
    user_username.short_description = 'Username'
    def user_full_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}" if obj.user.first_name and obj.user.last_name else "N/A"
    user_full_name.short_description = 'Full Name'
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'staff_id')
    list_filter = ('subjects_taught', 'date_employed')
    raw_id_fields = ('user',)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'student_id', 'date_of_birth', 'current_class', 'parent_username', 'gender')
    list_filter = ('current_class', 'gender')
    search_fields = ('first_name', 'last_name', 'student_id', 'parent__username', 'parent__first_name', 'parent__last_name')
    date_hierarchy = 'date_of_birth'
    def parent_username(self, obj):
        return obj.parent.username if obj.parent else "N/A"
    parent_username.short_description = 'Parent Username'
    raw_id_fields = ('current_class', 'parent',)


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'is_current')
    list_filter = ('is_current',)
    search_fields = ('name',)
    date_hierarchy = 'start_date'


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', '_class', 'term', 'max_score', 'date_given', 'recorded_by')
    list_filter = ('subject', '_class', 'term', 'recorded_by')
    search_fields = ('title', 'subject__name', '_class__name')
    date_hierarchy = 'date_given'
    raw_id_fields = ('subject', '_class', 'term', 'recorded_by')


@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = ('student', 'assignment', 'score_achieved', 'date_recorded', 'recorded_by')
    list_filter = ('assignment__subject', 'assignment___class', 'assignment__term', 'recorded_by')
    search_fields = ('student__first_name', 'student__last_name', 'assignment__title')
    date_hierarchy = 'date_recorded'
    raw_id_fields = ('student', 'assignment', 'recorded_by')


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('student', 'date', 'status', '_class', 'recorded_by', 'timestamp')
    list_filter = ('date', 'status', '_class', 'recorded_by')
    search_fields = ('student__first_name', 'student__last_name', '_class__name')
    date_hierarchy = 'date'
    raw_id_fields = ('student', '_class', 'recorded_by')
