from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.generic import ListView, View, CreateView, DetailView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.contrib import messages
from django.urls import reverse
from django.db.models import Q
from django.db import transaction, IntegrityError  # ADD THIS IMPORT
import json
from datetime import timedelta
from .utils import create_notification_safe
from .models import Notification, NotificationPreference, Ticket, TicketMessage, InternalMessage, MessageRecipient, Department, TicketWorkflow
from apps.inventory.models import StockItem
from .forms import NotificationPreferencesForm

User = get_user_model()

class NotificationListView(LoginRequiredMixin, ListView):
    model = Notification
    template_name = "notifications/notification_list.html"
    context_object_name = "notifications"
    paginate_by = 20

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by(
            "-created_at"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["unread_count"] = Notification.objects.filter(
            user=self.request.user, is_read=False
        ).count()
        return context


class MarkNotificationReadView(LoginRequiredMixin, View):
    def post(self, request, pk):
        try:
            notification = Notification.objects.get(id=pk, user=request.user)
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save()

            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": True})
            return redirect("notification-list")
        except Notification.DoesNotExist:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse(
                    {"success": False, "error": "Notification not found"}, status=404
                )
            return redirect("notification-list")


class MarkAllNotificationsReadView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            updated_count = Notification.objects.filter(
                user=request.user, is_read=False
            ).update(is_read=True, read_at=timezone.now())

            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse(
                    {
                        "success": True,
                        "message": f"Marked {updated_count} notifications as read",
                    }
                )
            return redirect("notification-list")
        except Exception as e:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "error": str(e)}, status=500)
            return redirect("notification-list")


class UnreadNotificationCountView(LoginRequiredMixin, View):
    def get(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return JsonResponse({"count": count})

class DeleteNotificationView(LoginRequiredMixin, View):
    def delete(self, request, pk):
        try:
            notification = Notification.objects.get(id=pk, user=request.user)
            notification.delete()
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True})
            return redirect('notification-list')
        except Notification.DoesNotExist:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Notification not found'}, status=404)
            return redirect('notification-list')

class NotificationPreferencesView(LoginRequiredMixin, View):
    template_name = "notifications/notification_preferences.html"
    
    def get(self, request):
        from .forms import NotificationPreferencesForm
        from .models import NotificationPreference
        
        # Get or create user preferences
        preferences, created = NotificationPreference.objects.get_or_create(
            user=request.user
        )
        form = NotificationPreferencesForm(instance=preferences)
        
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        
        preferences = NotificationPreference.objects.get(user=request.user)
        form = NotificationPreferencesForm(request.POST, instance=preferences)
        
        if form.is_valid():
            form.save()
            messages.success(request, "Notification preferences updated successfully.")
            return redirect('notification-preferences')
        
        return render(request, self.template_name, {'form': form})


class PendingNotificationsView(LoginRequiredMixin, View):
    def get(self, request):
        from datetime import timedelta

        recent_notifications = Notification.objects.filter(
            user=request.user,
            is_read=False,
            created_at__gte=timezone.now() - timedelta(minutes=5),
        )[:10]

        notifications_data = [
            {
                "id": notif.id,
                "title": notif.title,
                "message": notif.message,
                "type": notif.notification_type,
                "priority": notif.priority,
                "url": notif.action_url,
                "created_at": notif.created_at.isoformat(),
            }
            for notif in recent_notifications
        ]

        return JsonResponse({"success": True, "notifications": notifications_data})


class TicketListView(LoginRequiredMixin, ListView):
    model = Ticket
    template_name = "notifications/ticket_list.html"
    context_object_name = "tickets"
    paginate_by = 20

    def get_queryset(self):
        queryset = Ticket.objects.select_related(
            "created_by", "assigned_to", "assigned_department"
        )

        # Filter based on user role and permissions
        if not self.request.user.is_superuser:
            # Users see tickets they created or are assigned to
            queryset = queryset.filter(
                Q(created_by=self.request.user)
                | Q(assigned_to=self.request.user)
                | Q(assigned_department__manager=self.request.user)
            )

        # Apply filters
        status = self.request.GET.get("status")
        if status:
            queryset = queryset.filter(status=status)

        ticket_type = self.request.GET.get("ticket_type")
        if ticket_type:
            queryset = queryset.filter(ticket_type=ticket_type)

        priority = self.request.GET.get("priority")
        if priority:
            queryset = queryset.filter(priority=priority)

        assigned_to_me = self.request.GET.get("assigned_to_me")
        if assigned_to_me:
            queryset = queryset.filter(assigned_to=self.request.user)

        return queryset.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["ticket_types"] = Ticket.TICKET_TYPES
        context["status_choices"] = Ticket.TICKET_STATUS
        context["priority_choices"] = Ticket.PRIORITY_LEVELS

        # Statistics for dashboard
        if self.request.user.is_superuser:
            context["total_tickets"] = Ticket.objects.count()
            context["open_tickets"] = Ticket.objects.filter(status="open").count()
            context["overdue_tickets"] = Ticket.objects.filter(
                due_date__lt=timezone.now(), status__in=["open", "in_progress"]
            ).count()
        else:
            context["my_tickets"] = Ticket.objects.filter(
                Q(created_by=self.request.user) | Q(assigned_to=self.request.user)
            ).count()
            context["assigned_to_me"] = Ticket.objects.filter(
                assigned_to=self.request.user, status__in=["open", "in_progress"]
            ).count()

        return context


class TicketCreateView(LoginRequiredMixin, CreateView):
    model = Ticket
    template_name = "notifications/ticket_form.html"
    fields = ["title", "description", "ticket_type", "priority", "due_date"]

    def form_valid(self, form):
        form.instance.created_by = self.request.user

        # Auto-assign based on workflow
        try:
            workflow = TicketWorkflow.objects.filter(
                ticket_type=form.instance.ticket_type, is_active=True
            ).first()

            if workflow:
                form.instance.assigned_department = workflow.assigned_department
                if workflow.auto_assign and workflow.assigned_department.manager:
                    form.instance.assigned_to = workflow.assigned_department.manager
        except TicketWorkflow.DoesNotExist:
            pass

        response = super().form_valid(form)

        # Create notification for assigned user/department
        if form.instance.assigned_to and isinstance(form.instance.assigned_to, User):
            create_notification_safe(
                user=form.instance.assigned_to,
                title=f"New Message on Ticket: {self.ticket.ticket_number}",
                message=f"{self.request.user.username} posted a new message",
                notification_type="system",
                priority="medium",
                action_url=reverse("ticket-detail", kwargs={"pk": self.ticket.pk}),
            )

        messages.success(
            self.request, f"Ticket {form.instance.ticket_number} created successfully."
        )
        return response

    def get_success_url(self):
        return reverse("ticket-detail", kwargs={"pk": self.object.pk})


class TicketDetailView(LoginRequiredMixin, DetailView):
    model = Ticket
    template_name = "notifications/ticket_detail.html"
    context_object_name = "ticket"

    def get_queryset(self):
        return Ticket.objects.select_related(
            "created_by", "assigned_to", "assigned_department"
        ).prefetch_related("ticket_messages__user")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["messages"] = self.object.ticket_messages.select_related("user").all()
        context["can_edit"] = self.can_edit_ticket()
        return context

    def can_edit_ticket(self):
        ticket = self.get_object()
        user = self.request.user
        return (
            user == ticket.created_by
            or user == ticket.assigned_to
            or user.is_superuser
            or (
                ticket.assigned_department
                and user == ticket.assigned_department.manager
            )
        )


class TicketUpdateView(LoginRequiredMixin, UpdateView):
    model = Ticket
    template_name = "notifications/ticket_form.html"
    fields = [
        "title",
        "description",
        "ticket_type",
        "priority",
        "status",
        "assigned_to",
        "assigned_department",
        "due_date",
    ]

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Ticket.objects.all()
        return Ticket.objects.filter(
            Q(created_by=self.request.user)
            | Q(assigned_to=self.request.user)
            | Q(assigned_department__manager=self.request.user)
        )

    def form_valid(self, form):
        old_status = self.get_object().status
        new_status = form.cleaned_data["status"]

        response = super().form_valid(form)

        # Track status changes
        if old_status != new_status:
            if new_status == "resolved":
                self.object.resolved_at = timezone.now()
            elif new_status == "closed":
                self.object.closed_at = timezone.now()
            self.object.save()

            # Notify relevant users of status change
            self.notify_status_change(old_status, new_status)

        messages.success(
            self.request, f"Ticket {self.object.ticket_number} updated successfully."
        )
        return response

    def notify_status_change(self, old_status, new_status):
        users_to_notify = set()

        # Notify creator and assignee - ensure they are User instances
        users_to_notify.add(self.object.created_by)
        if self.object.assigned_to and isinstance(self.object.assigned_to, User):
            users_to_notify.add(self.object.assigned_to)

        for user in users_to_notify:
            if isinstance(user, User):
                create_notification_safe(
                    user=user,
                    title=f"Ticket Status Updated: {self.object.ticket_number}",
                    message=f"{self.request.user.username} posted a new message",
                    notification_type="system",
                    priority="medium",
                    action_url=reverse("ticket-detail", kwargs={"pk": self.ticket.pk}),
                )


class AddTicketMessageView(LoginRequiredMixin, CreateView):
    model = TicketMessage
    template_name = "notifications/add_ticket_message.html"
    fields = ["message", "is_internal_note", "attachments"]

    def dispatch(self, request, *args, **kwargs):
        self.ticket_id = kwargs.get("ticket_id")
        if not self.ticket_id:
            messages.error(request, "Ticket ID is required.")
            return redirect("ticket-list")

        self.ticket = get_object_or_404(Ticket, pk=self.ticket_id)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.ticket = self.ticket
        form.instance.user = self.request.user

        response = super().form_valid(form)

        # Notify other ticket participants
        self.notify_participants()

        messages.success(self.request, "Message added to ticket.")
        return response

    def notify_participants(self):
        participants = set()

        # Include ticket creator, assignee, and all message senders
        participants.add(self.ticket.created_by)
        if self.ticket.assigned_to:
            participants.add(self.ticket.assigned_to)

        # Add all users who have posted messages
        message_users = User.objects.filter(
            id__in=self.ticket.ticket_messages.values_list("user", flat=True).distinct()
        )
        participants.update(message_users)

        # Remove current user from notification
        participants.discard(self.request.user)

        for user in participants:
            # Ensure user is a User instance, not an ID
            if isinstance(user, User):
                create_notification_safe(
                    user=user,
                    title=f"New Message on Ticket: {self.ticket.ticket_number}",
                    message=f"{self.request.user.username} posted a new message",
                    notification_type="system",
                    priority="medium",
                    action_url=reverse("ticket-detail", kwargs={"pk": self.ticket.pk}),
                )

    def get_success_url(self):
        return reverse("ticket-detail", kwargs={"pk": self.ticket.pk})


class InternalMessageCreateView(LoginRequiredMixin, CreateView):
    model = InternalMessage
    template_name = "notifications/internal_message_form.html"
    fields = [
        "subject",
        "message",
        "message_type",
        "recipients",
        "is_urgent",
        "requires_confirmation",
    ]

    def form_valid(self, form):
        form.instance.sender = self.request.user

        # Save the message instance first (this creates the PK)
        self.object = form.save()

        # Get unique recipients and use set() to avoid duplicates
        recipients = list(set(form.cleaned_data["recipients"]))
        
        # Set recipients after the object has been saved
        self.object.recipients.set(recipients)

        # Create recipient records safely
        self.create_recipient_records(recipients)

        # Send notifications for urgent messages
        if form.cleaned_data["is_urgent"]:
            for recipient in recipients:
                if isinstance(recipient, User):
                    create_notification_safe(
                        user=recipient,
                        title=f"Urgent Message: {form.instance.subject}",
                        message=f"You have received an urgent message from {self.request.user.username}",
                        notification_type="system",
                        priority="high",
                        action_url=reverse("message-detail", kwargs={"pk": self.object.pk}),
                    )
        
        messages.success(self.request, "Message sent successfully.")
        return redirect(self.get_success_url())

    def create_recipient_records(self, recipients):
        """Safely create recipient records handling duplicates"""
        for recipient in recipients:
            if isinstance(recipient, User):
                try:
                    MessageRecipient.objects.get_or_create(
                        message=self.object, 
                        recipient=recipient,
                        defaults={'is_read': False}
                    )
                except IntegrityError:
                    # Handle case where record already exists
                    continue

    def get_success_url(self):
        # Ensure we have a valid object with PK
        if hasattr(self, 'object') and self.object and self.object.pk:
            return reverse("message-outbox")
        else:
            return reverse("message-inbox")


class MessageInboxView(LoginRequiredMixin, ListView):
    model = MessageRecipient
    template_name = "notifications/message_inbox.html"
    context_object_name = "received_messages"
    paginate_by = 20

    def get_queryset(self):
        return (
            MessageRecipient.objects.filter(recipient=self.request.user)
            .select_related("message", "message__sender")
            .order_by("-message__created_at")
        )


class MarkMessageReadView(LoginRequiredMixin, View):
    def post(self, request, pk):
        message_recipient = get_object_or_404(
            MessageRecipient, pk=pk, recipient=request.user
        )
        message_recipient.is_read = True
        message_recipient.read_at = timezone.now()
        message_recipient.save()

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        return redirect("message-inbox")


class ConfirmMessageView(LoginRequiredMixin, View):
    def post(self, request, pk):
        message_recipient = get_object_or_404(
            MessageRecipient, pk=pk, recipient=request.user
        )
        message_recipient.confirmed_at = timezone.now()
        message_recipient.save()

        # Notify sender of confirmation - ensure sender is a User instance
        sender = message_recipient.message.sender
        if isinstance(sender, User):
            create_notification_safe(
                user=sender,  
                title=f"Message Confirmed: {message_recipient.message.subject}",
                message=f"{self.request.user.username} confirmed receipt of your message",
                notification_type="system",
                priority="low",
                action_url=reverse("message-detail", kwargs={"pk": message_recipient.message.pk}),
            )

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        return redirect("message-inbox")


class TicketStatsAPIView(LoginRequiredMixin, View):
    """API endpoint for ticket statistics"""

    def get(self, request):
        try:
            # Base queryset based on user permissions
            if request.user.is_superuser:
                tickets = Ticket.objects.all()
            else:
                tickets = Ticket.objects.filter(
                    Q(created_by=request.user)
                    | Q(assigned_to=request.user)
                    | Q(assigned_department__manager=request.user)
                )

            # Calculate statistics
            total_tickets = tickets.count()
            open_tickets = tickets.filter(status="open").count()
            in_progress_tickets = tickets.filter(status="in_progress").count()
            resolved_tickets = tickets.filter(status="resolved").count()
            closed_tickets = tickets.filter(status="closed").count()

            # Priority breakdown
            urgent_tickets = tickets.filter(
                priority="urgent", status__in=["open", "in_progress"]
            ).count()
            high_priority_tickets = tickets.filter(
                priority="high", status__in=["open", "in_progress"]
            ).count()

            # Overdue tickets
            overdue_tickets = tickets.filter(
                due_date__lt=timezone.now(), status__in=["open", "in_progress"]
            ).count()

            # Average resolution time (for closed tickets)
            closed_tickets_with_dates = tickets.filter(
                status="closed", resolved_at__isnull=False, created_at__isnull=False
            )

            if closed_tickets_with_dates.exists():
                resolution_times = [
                    (ticket.resolved_at - ticket.created_at).total_seconds()
                    / 3600  # hours
                    for ticket in closed_tickets_with_dates
                ]
                avg_resolution_hours = sum(resolution_times) / len(resolution_times)
            else:
                avg_resolution_hours = 0

            # Department-wise breakdown (for admins)
            department_stats = []
            if request.user.is_superuser:
                departments = Department.objects.filter(is_active=True)
                for dept in departments:
                    dept_tickets = tickets.filter(assigned_department=dept)
                    department_stats.append(
                        {
                            "department": dept.name,
                            "total": dept_tickets.count(),
                            "open": dept_tickets.filter(
                                status__in=["open", "in_progress"]
                            ).count(),
                            "overdue": dept_tickets.filter(
                                due_date__lt=timezone.now(),
                                status__in=["open", "in_progress"],
                            ).count(),
                        }
                    )

            data = {
                "success": True,
                "stats": {
                    "total_tickets": total_tickets,
                    "by_status": {
                        "open": open_tickets,
                        "in_progress": in_progress_tickets,
                        "resolved": resolved_tickets,
                        "closed": closed_tickets,
                    },
                    "by_priority": {
                        "urgent": urgent_tickets,
                        "high": high_priority_tickets,
                    },
                    "overdue_tickets": overdue_tickets,
                    "avg_resolution_hours": round(avg_resolution_hours, 2),
                    "department_stats": department_stats,
                },
            }

            return JsonResponse(data)

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)


class UnreadMessageCountView(LoginRequiredMixin, View):
    """API endpoint for unread message count"""

    def get(self, request):
        try:
            unread_messages = MessageRecipient.objects.filter(
                recipient=request.user, is_read=False
            ).count()

            unread_ticket_messages = (
                TicketMessage.objects.filter(
                    ticket__in=Ticket.objects.filter(
                        Q(created_by=request.user) | Q(assigned_to=request.user)
                    ),
                    user__ne=request.user,  # Messages not sent by current user
                )
                .exclude(
                    # Exclude messages where user has already read them
                    # This is a simplified version - you might want to implement proper read tracking for ticket messages
                )
                .count()
            )

            return JsonResponse(
                {
                    "success": True,
                    "unread_messages": unread_messages,
                    "unread_ticket_messages": unread_ticket_messages,
                    "total_unread": unread_messages + unread_ticket_messages,
                }
            )

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)


class MessageOutboxView(LoginRequiredMixin, ListView):
    """View for sent messages"""

    model = InternalMessage
    template_name = "notifications/message_outbox.html"
    context_object_name = "sent_messages"
    paginate_by = 20

    def get_queryset(self):
        return (
            InternalMessage.objects.filter(sender=self.request.user)
            .prefetch_related("recipients", "recipient_entries")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add read statistics for each message
        messages_with_stats = []
        for message in context["sent_messages"]:
            total_recipients = message.recipients.count()
            read_recipients = message.recipient_entries.filter(is_read=True).count()
            confirmed_recipients = message.recipient_entries.filter(
                confirmed_at__isnull=False
            ).count()

            messages_with_stats.append(
                {
                    "message": message,
                    "total_recipients": total_recipients,
                    "read_recipients": read_recipients,
                    "confirmed_recipients": confirmed_recipients,
                    "read_percentage": (
                        (read_recipients / total_recipients * 100)
                        if total_recipients > 0
                        else 0
                    ),
                }
            )

        context["messages_with_stats"] = messages_with_stats
        return context


class MessageDetailView(LoginRequiredMixin, DetailView):
    """View for individual message details"""

    model = InternalMessage
    template_name = "notifications/message_detail.html"
    context_object_name = "message"

    def get_queryset(self):
        # Users can see messages they sent or received
        return InternalMessage.objects.filter(
            Q(sender=self.request.user) | Q(recipients=self.request.user)
        ).distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        message = self.get_object()

        # Mark as read if user is recipient
        if self.request.user in message.recipients.all():
            recipient_record = MessageRecipient.objects.get(
                message=message, recipient=self.request.user
            )
            if not recipient_record.is_read:
                recipient_record.is_read = True
                recipient_record.read_at = timezone.now()
                recipient_record.save()

        # Get recipient status
        recipient_status = []
        for recipient in message.recipients.all():
            recipient_record = MessageRecipient.objects.get(
                message=message, recipient=recipient
            )
            recipient_status.append(
                {
                    "recipient": recipient,
                    "is_read": recipient_record.is_read,
                    "read_at": recipient_record.read_at,
                    "confirmed_at": recipient_record.confirmed_at,
                }
            )

        context["recipient_status"] = recipient_status
        context["can_reply"] = message.message_type in ["direct", "group"]
        return context


class ReplyToMessageView(LoginRequiredMixin, CreateView):
    model = InternalMessage
    template_name = "notifications/message_reply.html"
    fields = ["message"]
    
    def dispatch(self, request, *args, **kwargs):
        self.parent_message = get_object_or_404(InternalMessage, pk=kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["parent_message"] = self.parent_message
        return context

    @transaction.atomic
    def form_valid(self, form):
        try:
            form.instance.sender = self.request.user
            form.instance.subject = f"Re: {self.parent_message.subject}"
            form.instance.message_type = self.parent_message.message_type
            form.instance.parent_message = self.parent_message

            # Save the message FIRST before setting recipients
            self.object = form.save()

            # Determine recipients
            if self.parent_message.message_type == "direct":
                # For direct messages, only reply to the sender
                recipients = [self.parent_message.sender]
            else:
                # For group messages, include all original recipients except current user
                recipients = list(set(self.parent_message.recipients.all()))
                if self.request.user in recipients:
                    recipients.remove(self.request.user)
                
                # Always include the original sender if they're not already in the list
                if self.parent_message.sender not in recipients:
                    recipients.append(self.parent_message.sender)

            # Set recipients and create records safely
            self.object.recipients.set(recipients)
            self.bulk_create_recipients_safe(recipients)

            # Send notifications for replies
            self.send_reply_notifications(recipients)

            messages.success(self.request, "Reply sent successfully.")
            return redirect(self.get_success_url())

        except IntegrityError as e:
            messages.error(self.request, "Error sending reply. Please try again.")
            return self.form_invalid(form)
        except Exception as e:
            messages.error(self.request, f"Unexpected error: {str(e)}")
            return self.form_invalid(form)

    def bulk_create_recipients_safe(self, recipients):
        """Bulk create recipients with duplicate handling"""
        existing_pairs = MessageRecipient.objects.filter(
            message=self.object, recipient__in=recipients
        ).values_list("recipient_id", flat=True)

        new_recipients = [
            recipient
            for recipient in recipients
            if recipient.id not in existing_pairs and isinstance(recipient, User)
        ]

        recipient_entries = [
            MessageRecipient(message=self.object, recipient=recipient, is_read=False)
            for recipient in new_recipients
        ]

        if recipient_entries:
            MessageRecipient.objects.bulk_create(recipient_entries)

    def send_reply_notifications(self, recipients):
        """Send notifications to recipients about the reply"""
        for recipient in recipients:
            if isinstance(recipient, User) and recipient != self.request.user:
                create_notification_safe(
                    user=recipient,
                    title=f"Reply to: {self.parent_message.subject}",
                    message=f"{self.request.user.username} replied to your message",
                    notification_type="system",
                    priority="medium",
                    action_url=reverse("message-detail", kwargs={"pk": self.object.pk}),
                )

    def get_success_url(self):
        # Ensure we have a valid object with PK before generating URL
        if hasattr(self, 'object') and self.object and self.object.pk:
            return reverse("message-detail", kwargs={"pk": self.object.pk})
        else:
            # Fallback to inbox if something went wrong
            messages.warning(self.request, "Reply sent but there was an issue with redirection.")
            return reverse("message-inbox")


class TicketAutoCompleteView(LoginRequiredMixin, View):
    """API for ticket autocomplete searches"""

    def get(self, request):
        query = request.GET.get("q", "")

        if not query or len(query) < 2:
            return JsonResponse({"results": []})

        tickets = Ticket.objects.filter(
            Q(ticket_number__icontains=query)
            | Q(title__icontains=query)
            | Q(description__icontains=query)
        )[
            :10
        ]  # Limit to 10 results

        results = [
            {
                "id": ticket.id,
                "text": f"{ticket.ticket_number} - {ticket.title}",
                "ticket_number": ticket.ticket_number,
                "title": ticket.title,
                "status": ticket.status,
            }
            for ticket in tickets
        ]

        return JsonResponse({"results": results})


class UserAutoCompleteView(LoginRequiredMixin, View):
    """API for user autocomplete in message recipients"""

    def get(self, request):
        query = request.GET.get("q", "")

        if not query or len(query) < 2:
            return JsonResponse({"results": []})

        User = get_user_model()
        users = User.objects.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query),
            is_active=True,
        )[:10]

        results = [
            {
                "id": user.id,
                "text": f"{user.get_full_name()} ({user.username}) - {user.email}",
                "username": user.username,
                "email": user.email,
                "full_name": user.get_full_name() or user.username,
            }
            for user in users
        ]

        return JsonResponse({"results": results})


class DepartmentTicketsAPIView(LoginRequiredMixin, View):
    """API for department-specific ticket statistics"""

    def get(self, request, department_id=None):
        try:
            if department_id:
                department = get_object_or_404(Department, id=department_id)
                tickets = Ticket.objects.filter(assigned_department=department)
            else:
                tickets = Ticket.objects.all()

            # Status breakdown for the last 30 days
            thirty_days_ago = timezone.now() - timedelta(days=30)

            recent_tickets = tickets.filter(created_at__gte=thirty_days_ago)

            status_data = {
                "open": recent_tickets.filter(status="open").count(),
                "in_progress": recent_tickets.filter(status="in_progress").count(),
                "resolved": recent_tickets.filter(status="resolved").count(),
                "closed": recent_tickets.filter(status="closed").count(),
            }

            # Weekly trend data
            weekly_data = []
            for i in range(4):  # Last 4 weeks
                week_start = timezone.now() - timedelta(weeks=i + 1)
                week_end = timezone.now() - timedelta(weeks=i)

                week_tickets = recent_tickets.filter(
                    created_at__range=[week_start, week_end]
                )

                weekly_data.append(
                    {
                        "week": f"Week {4-i}",
                        "created": week_tickets.count(),
                        "resolved": week_tickets.filter(status="resolved").count(),
                    }
                )

            return JsonResponse(
                {
                    "success": True,
                    "status_data": status_data,
                    "weekly_trend": weekly_data,
                    "total_recent_tickets": recent_tickets.count(),
                }
            )

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)


class BulkTicketUpdateView(LoginRequiredMixin, View):
    """API for bulk updating tickets"""

    def post(self, request):
        try:
            data = json.loads(request.body)
            ticket_ids = data.get("ticket_ids", [])
            action = data.get("action")
            new_value = data.get("value")

            if not ticket_ids or not action:
                return JsonResponse(
                    {"success": False, "error": "Missing required parameters"},
                    status=400,
                )

            # Get tickets that user has permission to update
            if request.user.is_superuser:
                tickets = Ticket.objects.filter(id__in=ticket_ids)
            else:
                tickets = Ticket.objects.filter(
                    Q(id__in=ticket_ids)
                    & (
                        Q(created_by=request.user)
                        | Q(assigned_to=request.user)
                        | Q(assigned_department__manager=request.user)
                    )
                )

            updated_count = 0

            if action == "update_status":
                for ticket in tickets:
                    ticket.status = new_value
                    if new_value == "resolved":
                        ticket.resolved_at = timezone.now()
                    elif new_value == "closed":
                        ticket.closed_at = timezone.now()
                    ticket.save()
                    updated_count += 1

            elif action == "update_priority":
                tickets.update(priority=new_value)
                updated_count = tickets.count()

            elif action == "assign_to":
                assignee = get_object_or_404(get_user_model(), id=new_value)
                for ticket in tickets:
                    ticket.assigned_to = assignee
                    ticket.save()
                    updated_count += 1

            return JsonResponse(
                {
                    "success": True,
                    "message": f"Successfully updated {updated_count} tickets",
                    "updated_count": updated_count,
                }
            )

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=500)
