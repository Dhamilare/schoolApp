from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='dashboard'),
    path('login/', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('assignments/', views.assignment_list, name='assignment_list'),
    path('assignments/create/', views.create_assignment, name='create_assignment'),
    path('assignments/<int:assignment_id>/update/', views.update_assignment, name='update_assignment'), 
    path('assignments/<int:assignment_id>/delete/', views.delete_assignment, name='delete_assignment'),
    path('assignments/<int:assignment_id>/submissions/', views.assignment_submissions, name='assignment_submissions'),
    path('submissions/<int:submission_id>/detail/', views.submission_detail, name='submission_detail'),
    path('assignments/<int:assignment_id>/scores/input/', views.input_scores, name='input_scores'),
    path('assignments/<int:assignment_id>/scores/save_ajax/', views.save_scores_ajax, name='save_scores_ajax'),
    path('assignments/<int:assignment_id>/create_mcq_questions/', views.create_mcq_questions, name='create_mcq_questions'),
    path('attendance/select_class/', views.select_class_for_attendance, name='select_class_for_attendance'),
    path('attendance/mark/<slug:class_slug>/<str:date_str>/', views.mark_attendance, name='mark_attendance'),
    path('attendance/save_ajax/<slug:class_slug>/<str:date_str>/', views.save_attendance_ajax, name='save_attendance_ajax'),
    path('attendance/history/', views.attendance_history, name='attendance_history'),
    path('report_card/pdf/<int:student_id>/<int:term_id>/', views.generate_report_card_pdf, name='generate_report_card_pdf'),
    path('parent-dashboard/', views.parent_dashboard, name='parent_dashboard'),
    path('api/teacher_dashboard_data/', views.teacher_dashboard_data, name='teacher_dashboard_data'),

    # Subject Management
    path('subjects/', views.subject_list, name='subject_list'), 
    path('subjects/create/', views.create_subject, name='create_subject'),
    path('subjects/update/<int:pk>/', views.update_subject, name='update_subject'), 
    path('subjects/delete/<int:pk>/', views.delete_subject, name='delete_subject'),

    path('students/dashboard/', views.student_dashboard, name='student_dashboard'),
    path('students/assignments/<int:assignment_id>/submit/', views.submit_assignment, name='submit_assignment'),
    path('students/create/', views.create_student, name='create_student'),
    path('students/list/', views.student_list, name='student_list'),
    path('students/update/<int:pk>/', views.update_student, name='update_student'),
    path('students/delete/<int:pk>/', views.delete_student, name='delete_student'),
]
