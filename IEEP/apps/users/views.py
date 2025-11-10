from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView as DjangoLoginView, LogoutView as DjangoLogoutView
from django.utils.decorators import method_decorator
from django.views.generic import ListView, DetailView, TemplateView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.contrib.auth.forms import PasswordChangeForm
from django.views import View
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.db import transaction
import secrets
import string
from .models import User, Role, AuditLog
from .forms import UserForm, CustomPasswordChangeForm, UserProfileForm


class AuthRootView(View):
    """Root view for authentication API"""
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

class LoginView(DjangoLoginView):
    template_name = 'users/login.html'
    redirect_authenticated_user = True
    
    def get_success_url(self):
        next_url = self.request.GET.get('next')
        if next_url:
            return next_url
        return reverse_lazy('dashboard')

    def form_valid(self, form):
        """Security: log login + IP"""
        response = super().form_valid(form)
        user = self.request.user

        # Log login
        AuditLog.objects.create(
            user=user,
            action='login',
            model_name='User',
            object_id=str(user.id),
            ip_address=self.get_client_ip(self.request)
        )

        # Handle AJAX requests
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'redirect_url': self.get_success_url()
            })

        messages.success(self.request, f"Welcome back, {user.get_full_name() or user.username}!")
        return response

    def form_invalid(self, form):
        # Handle AJAX requests
        if self.request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'Invalid username or password.'
            }, status=400)

        messages.error(self.request, "Invalid username or password.")
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['next'] = self.request.GET.get('next', '')
        return context

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

class LogoutView(View):
    def get(self, request):
        # Log logout before actually logging out
        if request.user.is_authenticated:
            AuditLog.objects.create(
                user=request.user,
                action='logout',
                model_name='User',
                object_id=str(request.user.id),
                ip_address=self.get_client_ip(request)
            )
        
        logout(request)
        messages.success(request, "You have been logged out successfully.")
        return redirect('login')

    def post(self, request):
        return self.get(request)

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

class UserProfileAPI(LoginRequiredMixin, View):
    """API endpoint for user profile data"""
    def get(self, request):
        # Check if user is authenticated
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        
        user = request.user
        return JsonResponse({
            'id': user.id,
            'username': user.username,
            'first_name': user.first_name or '',
            'last_name': user.last_name or '',
            'email': user.email or '',
            'profile_picture': user.profile_picture.url if user.profile_picture else None,
            'role': user.role.name if user.role else None,
        })


@method_decorator(login_required, name='dispatch')
class UserProfileView(LoginRequiredMixin, UpdateView):
    """View for user to update their own profile"""
    model = User
    form_class = UserProfileForm
    template_name = 'users/user_profile.html'
    success_url = reverse_lazy('profile')
    success_message = "Profile updated successfully."

    def get_object(self):
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['password_form'] = kwargs.get('password_form') or CustomPasswordChangeForm(self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        tab = request.POST.get('tab', 'info')

        if tab == 'info':
            form = UserProfileForm(request.POST, request.FILES, instance=self.object)
            password_form = CustomPasswordChangeForm(self.request.user)
            if form.is_valid():
                user = form.save()
                AuditLog.objects.create(
                    user=request.user,
                    action='update',
                    model_name='User',
                    object_id=str(user.id),
                    changes={'profile_picture': 'Updated'} if request.FILES else {},
                    ip_address=self.get_client_ip(request)
                )
                messages.success(request, self.success_message)
                return redirect(self.success_url)
            context = self.get_context_data(form=form, password_form=password_form)
            context['password_error'] = False
            return self.render_to_response(context)

        elif tab == 'password':
            form = UserProfileForm(instance=self.object)
            password_form = CustomPasswordChangeForm(self.request.user, request.POST)
            if password_form.is_valid():
                password_form.save()
                messages.success(request, "Password changed successfully.")
                AuditLog.objects.create(
                    user=request.user,
                    action='update',
                    model_name='User',
                    object_id=str(request.user.id),
                    changes={'password': 'Changed'},
                    ip_address=self.get_client_ip(request)
                )
                return redirect(self.success_url)
            context = self.get_context_data(form=form, password_form=password_form)
            context['password_error'] = True
            return self.render_to_response(context)

        return redirect(self.success_url)

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


@method_decorator(login_required, name='dispatch')
class UserListView(LoginRequiredMixin, ListView):
    """List all users in the system"""
    model = User
    template_name = 'users/user_list.html'
    context_object_name = 'users'
    paginate_by = 20

    def get_queryset(self):
        return User.objects.select_related('role').order_by('-date_joined')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_users'] = User.objects.count()
        context['active_users'] = User.objects.filter(is_active=True).count()
        return context


@method_decorator(login_required, name='dispatch')
class UserDetailView(LoginRequiredMixin, DetailView):
    """Detail view for a specific user"""
    model = User
    template_name = 'users/user_detail.html'
    context_object_name = 'user'

    def get_queryset(self):
        return User.objects.select_related('role')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get user's recent activities
        context['recent_activities'] = AuditLog.objects.filter(
            user=self.object
        ).order_by('-timestamp')[:10]
        return context


@method_decorator(login_required, name='dispatch')
class UserCreateView(LoginRequiredMixin, CreateView):
    """Create a new user"""
    model = User
    form_class = UserForm
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('user-list')

    def form_valid(self, form):
        with transaction.atomic():
            user = form.save()
            AuditLog.objects.create(
                user=self.request.user,
                action='create',
                model_name='User',
                object_id=str(user.id),
                ip_address=self.get_client_ip(self.request)
            )
            messages.success(self.request, 'User created successfully.')
        return redirect(self.success_url)

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


@method_decorator(login_required, name='dispatch')
class UserUpdateView(LoginRequiredMixin, UpdateView):
    """Update an existing user"""
    model = User
    form_class = UserForm
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('user-list')

    def get_queryset(self):
        # Allow only admins to edit others
        if self.request.user.role and self.request.user.role.name == 'admin':
            return User.objects.all()
        return User.objects.filter(pk=self.request.user.pk)

    def form_valid(self, form):
        with transaction.atomic():
            user = form.save()
            AuditLog.objects.create(
                user=self.request.user,
                action='update',
                model_name='User',
                object_id=str(user.id),
                changes={'profile_picture': 'Updated'} if self.request.FILES else {},
                ip_address=self.get_client_ip(self.request)
            )
            messages.success(self.request, 'User updated successfully.')
        return redirect(self.success_url)

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


@method_decorator(login_required, name='dispatch')
class UserToggleActiveView(LoginRequiredMixin, View):
    """Toggle user active status"""
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

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


@method_decorator(login_required, name='dispatch')
class UserResetPasswordView(LoginRequiredMixin, View):
    """Reset user password to a random one"""
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        
        # Generate random password
        alphabet = string.ascii_letters + string.digits
        new_password = ''.join(secrets.choice(alphabet) for _ in range(12))
        
        user.set_password(new_password)
        user.save()
        
        AuditLog.objects.create(
            user=request.user,
            action='update',
            model_name='User',
            object_id=str(user.id),
            changes={'password': {'old': '***', 'new': '*** (reset)'}},
            ip_address=self.get_client_ip(request)
        )
        
        messages.success(
            request, 
            f"Password reset for {user.username}. New password: <code class='bg-gray-100 px-2 py-1 rounded'>{new_password}</code>"
        )
        return redirect('user-list')

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


@method_decorator(login_required, name='dispatch')
class RoleListView(LoginRequiredMixin, ListView):
    """List all roles in the system"""
    model = Role
    template_name = 'users/role_list.html'
    context_object_name = 'roles'

    def get_queryset(self):
        return Role.objects.annotate(
            user_count=Count('users')
        ).order_by('name')


@method_decorator(login_required, name='dispatch')
class AuditLogListView(LoginRequiredMixin, ListView):
    """List all audit logs with filtering options"""
    model = AuditLog
    template_name = 'users/audit_log_list.html'
    context_object_name = 'audit_logs'
    paginate_by = 50
    ordering = ['-timestamp']

    def get_queryset(self):
        queryset = super().get_queryset().select_related('user')
        
        # Filter by user
        user_id = self.request.GET.get('user')
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        # Filter by action
        action = self.request.GET.get('action')
        if action:
            queryset = queryset.filter(action=action)
        
        # Filter by date range
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        if start_date:
            queryset = queryset.filter(timestamp__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__date__lte=end_date)
        
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['users'] = User.objects.all()
        context['actions'] = AuditLog.objects.values_list('action', flat=True).distinct()
        return context
