# quality/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('checklists/', views.QCChecklistListView.as_view(), name='qc-checklist-list'),
    path('qc-records/', views.QCRecordListView.as_view(), name='qc-record-list'),
    path('qc-records/<int:pk>/', views.QCRecordDetailView.as_view(), name='qc-record-detail'),
    path('failed-qc/', views.FailedQCListView.as_view(), name='failed-qc-list'),
]