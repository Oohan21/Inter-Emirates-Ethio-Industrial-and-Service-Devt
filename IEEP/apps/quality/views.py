# quality/views.py
from django.views.generic import ListView, DetailView
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from .models import QCChecklist, QCRecord

@method_decorator(login_required, name='dispatch')
class QCChecklistListView(ListView):
    model = QCChecklist
    template_name = 'quality/checklist_list.html'
    context_object_name = 'checklists'

@method_decorator(login_required, name='dispatch')
class QCRecordListView(ListView):
    model = QCRecord
    template_name = 'quality/qc_record_list.html'
    context_object_name = 'qc_records'
    ordering = ['-created_at']

@method_decorator(login_required, name='dispatch')
class QCRecordDetailView(DetailView):
    model = QCRecord
    template_name = 'quality/qc_record_detail.html'
    context_object_name = 'qc_record'

@method_decorator(login_required, name='dispatch')
class FailedQCListView(ListView):
    model = QCRecord
    template_name = 'quality/failed_qc_list.html'
    context_object_name = 'failed_records'

    def get_queryset(self):
        return QCRecord.objects.filter(status='failed')