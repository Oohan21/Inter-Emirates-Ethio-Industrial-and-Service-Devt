# users/views.py
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, TemplateView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views import View
from django.http import JsonResponse
from .models import User, Role, AuditLog
from .forms import UserForm
from django.contrib.auth.views import PasswordResetView
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages

class LoginView(View):
    def post(self, request):
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            # Log the login action
            AuditLog.objects.create(
                user=user,
                action='login',
                model_name='User',
                object_id=str(user.id),
                ip_address=self.get_client_ip(request)
            )
            return JsonResponse({
                'success': True,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'role': user.role.name if user.role else None
                }
            })
        return JsonResponse({'success': False, 'error': 'Invalid credentials'})

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

class LogoutView(View):
    def post(self, request):
        if request.user.is_authenticated:
            # Log the logout action
            AuditLog.objects.create(
                user=request.user,
                action='logout',
                model_name='User',
                object_id=str(request.user.id),
                ip_address=self.get_client_ip(request)
            )
            logout(request)
        return JsonResponse({'success': True})

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

class AuthRootView(View):
    def get(self, request):
        return JsonResponse({
            'message': 'Authentication API',
            'endpoints': {
                'login': '/api/auth/login/',
                'logout': '/api/auth/logout/',
                'profile': '/api/auth/profile/',
                'users': '/api/auth/users/',
                'roles': '/api/auth/roles/',
                'audit_logs': '/api/auth/audit-logs/'
            }
        })

@method_decorator(login_required, name='dispatch')
class UserProfileView(View):
    def get(self, request):
        user = request.user
        return JsonResponse({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role': user.role.name if user.role else None,
            'department': user.department,
            'phone': user.phone
        })

@method_decorator(login_required, name='dispatch')
class UserListView(ListView):
    model = User
    template_name = 'users/user_list.html'
    context_object_name = 'users'

@method_decorator(login_required, name='dispatch')
class UserDetailView(DetailView):
    model = User
    template_name = 'users/user_detail.html'
    context_object_name = 'user'

@method_decorator(login_required, name='dispatch')
class RoleListView(ListView):
    model = Role
    template_name = 'users/role_list.html'
    context_object_name = 'roles'

@method_decorator(login_required, name='dispatch')
class AuditLogListView(ListView):
    model = AuditLog
    template_name = 'users/audit_log_list.html'
    context_object_name = 'audit_logs'
    paginate_by = 50
    ordering = ['-timestamp']

class UserCreateView(LoginRequiredMixin, CreateView):
    model = User
    form_class = UserForm
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('user-list')

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditLog.objects.create(
            user=self.request.user,
            action='create',
            model_name='User',
            object_id=str(self.object.id),
            object_repr=str(self.object),
            ip_address=self.get_client_ip(self.request)
        )
        return response
    
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

class UserUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = UserForm
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('user-list')

    def form_valid(self, form):
        old_user = User.objects.get(pk=self.object.pk)
        response = super().form_valid(form)
        changes = {}
        for field in form.changed_data:
            changes[field] = {
                'old': str(getattr(old_user, field)),
                'new': str(getattr(self.object, field))
            }
        if changes:
            AuditLog.objects.create(
                user=self.request.user,
                action='update',
                model_name='User',
                object_id=str(self.object.id),
                object_repr=str(self.object),
                changes=changes,
                ip_address=self.get_client_ip(self.request)
            )
        return response

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = self.get_object()
        return kwargs
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

class UserToggleActiveView(LoginRequiredMixin, View):
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        old_status = user.is_active
        user.is_active = not user.is_active
        user.save()

        AuditLog.objects.create(
            user=request.user,
            action='update',
            model_name='User',
            object_id=str(user.id),
            object_repr=str(user),
            changes={'is_active': {'old': old_status, 'new': user.is_active}},
            ip_address=self.get_client_ip(request) 
        )
        messages.success(request, f"User {'activated' if user.is_active else 'deactivated'}.")
        return redirect('user-list')

    # ADD THIS METHOD INSIDE THE CLASS
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

class UserResetPasswordView(LoginRequiredMixin, View):
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        import secrets, string
        new_pass = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
        user.set_password(new_pass)
        user.save()
        AuditLog.objects.create(
            user=request.user,
            action='update',
            model_name='User',
            object_id=str(user.id),
            changes={'password': {'old': '***', 'new': '*** (reset)'}},
            ip_address=self.get_client_ip(request)
        )
        messages.success(request, f"Password reset for {user.username}. New: <code class='bg-gray-100 px-2 py-1 rounded'>{new_pass}</code>")
        return redirect('user-list')
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')
