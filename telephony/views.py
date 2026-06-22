from django.conf import settings
import logging
import requests
from datetime import datetime

from django.db.models import Avg, Q
from django.http import HttpResponse

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from accounts.permissions import has_dynamic_permission

from .models import VoxbayCallLog, VoxbayAgent
from .serializers import (
    VoxbayCallLogSerializer,
    VoxbayAgentSerializer,
    CallStatsSerializer,
    ClickToCallSerializer,
)

logger = logging.getLogger(__name__)

VOXBAY_CLICK_TO_CALL_URL  = "https://x.voxbay.com/api/click_to_call"
VOXBAY_RECORDING_BASE_URL = "https://x.voxbay.com:81/callcenter/"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_dt(date_str, time_str=None):
    if not date_str and time_str:
        date_str = time_str
        time_str = None
        
    if not date_str:
        return None
        
    combined = f"{date_str} {time_str}".strip() if time_str else date_str.strip()
    for fmt in (
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d %H:%M",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%Y/%m/%d",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(combined, fmt)
        except ValueError:
            continue
    logger.warning(f"[Voxbay] Could not parse datetime: '{combined}'")
    return None


def _safe_int(val):
    try:
        return int(val) if val not in (None, "", "None") else None
    except (ValueError, TypeError):
        return None


def _resolve_recording_url(raw_url):
    if not raw_url:
        return None
    raw_url = raw_url.strip()
    if raw_url.startswith("http://") or raw_url.startswith("https://"):
        return raw_url
    return VOXBAY_RECORDING_BASE_URL + raw_url


def process_voxbay_call_log(obj):
    if obj.call_type != 'incoming':
        return

    caller_number = obj.caller_number
    if not caller_number:
        return

    from leads.models import Lead, FollowUp
    from accounts.models import User
    from django.utils import timezone

    agent_user = None
    if obj.agent_number:
        agent_user = User.objects.filter(voxbay_number=obj.agent_number).first()

    existing_lead = Lead.objects.filter(phone=caller_number).first()

    if obj.call_status == 'ANSWER':
        if not existing_lead and agent_user:
            existing_lead = Lead.objects.create(
                name=f"Voxbay Caller - {caller_number}",
                phone=caller_number,
                source='VOXBAY CALL',
                status='ENQUIRY',
                assigned_to=agent_user
            )

        if existing_lead and agent_user:
            duration_str = str(obj.duration) + 's' if obj.duration else 'Unknown'
            notes = f"Answered Call\nDuration: {duration_str}\n"
            if obj.recording_url:
                notes += f"Recording: {obj.recording_url}\n"
            notes += f"\nCall UUID: {obj.call_uuid}"

            if not FollowUp.objects.filter(lead=existing_lead, assigned_to=agent_user, notes__contains=obj.call_uuid, status='contacted').exists():
                FollowUp.objects.create(
                    lead=existing_lead,
                    assigned_to=agent_user,
                    follow_up_date=obj.created_at.date() if obj.created_at else timezone.now().date(),
                    followup_type='call',
                    status='contacted',
                    priority='medium',
                    notes=notes,
                )
    else:
        if existing_lead:
            answered_exists = VoxbayCallLog.objects.filter(call_uuid=obj.call_uuid, call_status='ANSWER').exists()
            if not answered_exists:
                notes = f"Missed Call from Lead\nCall UUID: {obj.call_uuid}"
                lead_owner = existing_lead.assigned_to
                if lead_owner and not FollowUp.objects.filter(lead=existing_lead, status='pending', notes__contains=obj.call_uuid).exists():
                    FollowUp.objects.create(
                        lead=existing_lead,
                        assigned_to=lead_owner,
                        follow_up_date=timezone.now().date(),
                        followup_type='call',
                        status='pending',
                        priority='high',
                        notes=notes,
                    )



def _date_filter(qs, request):
    from django.utils.dateparse import parse_datetime, parse_date
    from_str = request.query_params.get("from")
    to_str   = request.query_params.get("to")

    def _parse(s):
        return parse_datetime(s) or (
            datetime.combine(parse_date(s), datetime.min.time()) if parse_date(s) else None
        )

    if from_str:
        dt = _parse(from_str)
        if dt:
            qs = qs.filter(created_at__gte=dt)
    if to_str:
        dt = _parse(to_str)
        if dt:
            qs = qs.filter(created_at__lte=dt)
    return qs


# ─── Agent directory ──────────────────────────────────────────────────────────

class VoxbayAgentListView(APIView):
    """
    GET  /api/voxbay/agents/
        Returns all active agents as a flat list.
        Also supports ?format=map to return a phone_number→name dict
        which the frontend can use for quick lookups.

    POST /api/voxbay/agents/
        Create a new agent mapping.
        Body: { name, phone_number, extension, did_number, department }

    PUT  /api/voxbay/agents/
        Bulk-upsert agents.
        Body: [ { name, phone_number, ... }, ... ]
        Useful for syncing from Voxbay's user list in one shot.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        qs = VoxbayAgent.objects.filter(is_active=True)

        # ?output=map  →  { "918089040107": "Shahida Beevi AM HQ", ... }
        if request.query_params.get("output") == "map":
            mapping = {a.phone_number: a.name for a in qs}
            # also index by extension so both keys work
            for a in qs:
                if a.extension:
                    mapping.setdefault(a.extension, a.name)
            return Response(mapping)

        return Response(VoxbayAgentSerializer(qs, many=True).data)

    def post(self, request):
        serializer = VoxbayAgentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def put(self, request):
        """Bulk upsert: list of agent dicts keyed by phone_number."""
        items = request.data
        if not isinstance(items, list):
            return Response({"error": "Expected a list."}, status=status.HTTP_400_BAD_REQUEST)

        created_count = updated_count = 0
        errors = []
        for item in items:
            phone = item.get("phone_number", "").strip()
            if not phone:
                errors.append({"item": item, "error": "phone_number required"})
                continue
            agent, created = VoxbayAgent.objects.update_or_create(
                phone_number=phone,
                defaults={
                    "name":       item.get("name", ""),
                    "extension":  item.get("extension") or None,
                    "did_number": item.get("did_number") or None,
                    "department": item.get("department") or None,
                    "is_active":  item.get("is_active", True),
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        return Response({
            "created": created_count,
            "updated": updated_count,
            "errors":  errors,
        })


class VoxbayAgentDetailView(APIView):
    """GET / PATCH / DELETE a single agent by pk."""
    permission_classes = [AllowAny]

    def _get(self, pk):
        try:
            return VoxbayAgent.objects.get(pk=pk)
        except VoxbayAgent.DoesNotExist:
            return None

    def get(self, request, pk):
        agent = self._get(pk)
        if not agent:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(VoxbayAgentSerializer(agent).data)

    def patch(self, request, pk):
        agent = self._get(pk)
        if not agent:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = VoxbayAgentSerializer(agent, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        agent = self._get(pk)
        if not agent:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        agent.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ─── Webhook ──────────────────────────────────────────────────────────────────

class VoxbayWebhookView(APIView):
    permission_classes     = [AllowAny]
    authentication_classes = []

    def post(self, request):
        data = request.data
        if not data:
            data = request.query_params

        raw_body = ""
        try:
            raw_body = request.body.decode("utf-8")
        except Exception:
            raw_body = "<undecodable body>"

        if data:
            logger.info(f"[Voxbay Webhook] payload={dict(data)}")
        else:
            logger.info(f"[Voxbay Webhook] payload is empty. raw_body={raw_body}")

        call_type = (
            "outgoing"
            if (data.get("extension") or data.get("destination"))
            else "incoming"
        )

        call_uuid = (
            data.get("CallUUID")
            or data.get("callUUID")
            or data.get("callUUlD")
        )

        call_date  = data.get("callDate") or data.get("date")
        call_start = _parse_dt(call_date, data.get("callStartTime"))
        call_end   = _parse_dt(call_date, data.get("callEndTime"))

        defaults = {}

        def _set(key, val):
            if val not in (None, "", "None"):
                defaults[key] = val

        _set("call_type",             call_type)
        _set("call_status",           data.get("callStatus") or data.get("status"))
        _set("duration",              _safe_int(
                                          data.get("totalCallDuration") or data.get("duration")
                                      ))
        _set("conversation_duration", _safe_int(data.get("conversationDuration")))
        _set("recording_url",         _resolve_recording_url(
                                          data.get("recording_URL") or data.get("recording_url")
                                      ))
        if call_start:
            defaults["call_start"] = call_start
        if call_end:
            defaults["call_end"] = call_end

        if call_type == "incoming":
            _set("called_number",      data.get("calledNumber"))
            _set("caller_number",      data.get("callerNumber"))
            _set("agent_number",       data.get("AgentNumber") or data.get("agentNumber"))
            _set("dtmf",               data.get("dtmf"))
            _set("transferred_number", data.get("transferredNumber"))
        else:
            _set("extension",     data.get("extension"))
            _set("destination",   data.get("destination"))
            _set("caller_id",     data.get("callerid"))
            _set("caller_number", data.get("callerid"))

        if call_uuid:
            obj, created = VoxbayCallLog.objects.update_or_create(
                call_uuid=call_uuid,
                defaults=defaults,
            )
            logger.info(
                f"[Voxbay Webhook] {'created' if created else 'updated'} "
                f"CallLog id={obj.id} uuid={call_uuid}"
            )
            try:
                process_voxbay_call_log(obj)
            except Exception as e:
                logger.error(f"[Voxbay] Error processing call log for lead generation: {e}")
        else:
            logger.warning(
                f"[Voxbay Webhook] no UUID in payload – rejecting. raw_body={raw_body}"
            )
            return Response({"error": "Missing CallUUID"}, status=status.HTTP_400_BAD_REQUEST)

        return HttpResponse("success", content_type="text/plain")


# ─── Call Log List ────────────────────────────────────────────────────────────

class CallLogListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = VoxbayCallLog.objects.all()

        if not has_dynamic_permission(request.user, 'voxbay:read_all'):
            if has_dynamic_permission(request.user, 'voxbay:read_own'):
                voxbay_number = getattr(request.user, 'voxbay_number', None)
                agent_numbers = []
                if voxbay_number:
                    agent_numbers.append(voxbay_number)
                
                from leads.models import Lead
                assigned_phones = list(Lead.objects.filter(
                    Q(assigned_to=request.user) | Q(sub_assigned_to=request.user)
                ).values_list('phone', flat=True))
                
                qs = qs.filter(
                    Q(agent_number__in=agent_numbers) |
                    Q(extension__in=agent_numbers) |
                    Q(caller_number__in=assigned_phones) |
                    Q(called_number__in=assigned_phones)
                )
            else:
                qs = qs.none()

        qs = _date_filter(qs, request)

        call_type = request.query_params.get("call_type")
        if call_type in ("incoming", "outgoing"):
            qs = qs.filter(call_type=call_type)

        call_status = request.query_params.get("call_status")
        if call_status:
            qs = qs.filter(call_status__iexact=call_status)

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(caller_number__icontains=search)  |
                Q(called_number__icontains=search)  |
                Q(agent_number__icontains=search)   |
                Q(destination__icontains=search)    |
                Q(extension__icontains=search)      |
                Q(call_uuid__icontains=search)
            )

        ordering = request.query_params.get("ordering", "-created_at")
        allowed_orderings = {
            "created_at", "-created_at",
            "duration",   "-duration",
            "call_status",
        }
        if ordering in allowed_orderings:
            qs = qs.order_by(ordering)

        try:
            page      = max(1, int(request.query_params.get("page", 1)))
            page_size = min(200, max(1, int(request.query_params.get("page_size", 20))))
        except (ValueError, TypeError):
            page, page_size = 1, 20

        total  = qs.count()
        offset = (page - 1) * page_size
        qs     = qs[offset: offset + page_size]

        serializer = VoxbayCallLogSerializer(qs, many=True)
        return Response({
            "count":     total,
            "page":      page,
            "page_size": page_size,
            "results":   serializer.data,
        })


# ─── Call Log Detail ──────────────────────────────────────────────────────────

class CallLogDetailView(APIView):
    permission_classes = [AllowAny]

    def _get_object(self, lookup, by_uuid=False):
        try:
            if by_uuid:
                return VoxbayCallLog.objects.get(call_uuid=lookup)
            return VoxbayCallLog.objects.get(pk=lookup)
        except VoxbayCallLog.DoesNotExist:
            return None

    def get(self, request, pk=None, uuid=None):
        obj = self._get_object(uuid, by_uuid=True) if uuid else self._get_object(pk)
        if obj is None:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(VoxbayCallLogSerializer(obj).data)


# ─── Call Statistics ──────────────────────────────────────────────────────────

class CallStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = VoxbayCallLog.objects.all()
        
        if not has_dynamic_permission(request.user, 'voxbay:read_all'):
            if has_dynamic_permission(request.user, 'voxbay:read_own'):
                user_phone = getattr(request.user, 'phone', None)
                agent_numbers = []
                if user_phone:
                    base_phone = user_phone[-10:] if len(user_phone) >= 10 else user_phone
                    agents = VoxbayAgent.objects.filter(phone_number__endswith=base_phone)
                    agent_numbers = list(agents.values_list('phone_number', flat=True))
                    agent_numbers.extend([e for e in agents.values_list('extension', flat=True) if e])
                
                from leads.models import Lead
                assigned_phones = list(Lead.objects.filter(
                    Q(assigned_to=request.user) | Q(sub_assigned_to=request.user)
                ).values_list('phone', flat=True))
                
                qs = qs.filter(
                    Q(agent_number__in=agent_numbers) |
                    Q(extension__in=agent_numbers) |
                    Q(caller_number__in=assigned_phones) |
                    Q(called_number__in=assigned_phones)
                )
            else:
                qs = qs.none()
                
        qs = _date_filter(qs, request)

        call_type = request.query_params.get("call_type")
        if call_type in ("incoming", "outgoing"):
            qs = qs.filter(call_type=call_type)

        total       = qs.count()
        answered    = qs.filter(call_status="ANSWERED").count()
        missed      = qs.filter(call_status__in=["NOANSWER", "CANCEL", "MISSED"]).count()
        busy        = qs.filter(call_status="BUSY").count()
        congestion  = qs.filter(call_status="CONGESTION").count()
        chanunavail = qs.filter(call_status="CHANUNAVAIL").count()
        incoming    = qs.filter(call_type="incoming").count()
        outgoing    = qs.filter(call_type="outgoing").count()

        avg_result = qs.filter(
            call_status="ANSWERED",
            duration__isnull=False,
        ).aggregate(avg=Avg("duration"))
        avg_duration = round(avg_result["avg"], 1) if avg_result["avg"] else 0.0

        data = {
            "total":        total,
            "answered":     answered,
            "missed":       missed,
            "busy":         busy,
            "congestion":   congestion,
            "chanunavail":  chanunavail,
            "incoming":     incoming,
            "outgoing":     outgoing,
            "avg_duration": avg_duration,
            "success_rate": round(answered / total * 100, 1) if total else 0.0,
        }

        serializer = CallStatsSerializer(data)
        return Response(serializer.data)


# ─── Click-to-Call ────────────────────────────────────────────────────────────

class ClickToCallView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ClickToCallSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Validation failed", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        validated = serializer.validated_data
        
        voxbay_uid = getattr(settings, 'VOXBAY_UID', None)
        voxbay_upin = getattr(settings, 'VOXBAY_UPIN', None)
        
        if not voxbay_uid or not voxbay_upin:
            logger.error("[Click-to-Call] VOXBAY_UID or VOXBAY_UPIN missing from settings")
            return Response(
                {"error": "Server configuration error: Voxbay credentials not set"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        params = {
            "id_dept":     0,
            "uid":         voxbay_uid,
            "upin":        voxbay_upin,
            "user_no":     validated["user_no"],
            "destination": validated["destination"],
            "callerid":    validated["callerid"],
        }
        if validated.get("source"):
            params["source"] = validated["source"]

        logger.info(f"[Click-to-Call] params={params}")

        try:
            resp = requests.get(VOXBAY_CLICK_TO_CALL_URL, params=params, timeout=10)
            resp.raise_for_status()
            return Response({
                "success":         True,
                "voxbay_response": resp.text,
                "status_code":     resp.status_code,
            })
        except requests.Timeout:
            logger.error("[Click-to-Call] Voxbay API timed out")
            return Response(
                {"error": "Voxbay API timed out"},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )
        except requests.HTTPError as e:
            logger.error(f"[Click-to-Call] HTTP error: {e}")
            return Response(
                {
                    "success":         False,
                    "voxbay_response": resp.text,
                    "status_code":     resp.status_code,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except requests.RequestException as e:
            logger.error(f"[Click-to-Call] RequestException: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

# ─── Unique Missed Calls ──────────────────────────────────────────────────────

class UnassignedMissedCallsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not has_dynamic_permission(request.user, "voxbay:admin"):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        # Get all incoming missed calls (not ANSWER)
        missed_logs = VoxbayCallLog.objects.filter(call_type='incoming').exclude(call_status='ANSWER')
        missed_logs = _date_filter(missed_logs, request)
        
        # Get all CallUUIDs that HAVE been answered
        answered_uuids = VoxbayCallLog.objects.filter(call_type='incoming', call_status='ANSWER').values_list('call_uuid', flat=True)
        
        # Exclude those that were eventually answered
        unique_missed = missed_logs.exclude(call_uuid__in=answered_uuids).order_by('-created_at')

        # To avoid showing the same ring multiple times if it rang 3 agents and none answered:
        # We can group by CallUUID and return the latest
        unique_missed_dict = {}
        for log in unique_missed:
            if log.call_uuid not in unique_missed_dict:
                unique_missed_dict[log.call_uuid] = log

        logs_to_return = list(unique_missed_dict.values())
        serializer = VoxbayCallLogSerializer(logs_to_return, many=True)
        return Response(serializer.data)


class AssignMissedCallView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, call_uuid):
        if not has_dynamic_permission(request.user, "voxbay:admin"):
            return Response({"error": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        agent_id = request.data.get('agent_id')
        if not agent_id:
            return Response({"error": "agent_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        from accounts.models import User
        from leads.models import Lead, FollowUp
        from django.utils import timezone

        agent = User.objects.filter(id=agent_id).first()
        if not agent:
            return Response({"error": "Agent not found"}, status=status.HTTP_404_NOT_FOUND)

        log = VoxbayCallLog.objects.filter(call_uuid=call_uuid).first()
        if not log:
            return Response({"error": "Call log not found"}, status=status.HTTP_404_NOT_FOUND)

        caller_number = log.caller_number
        existing_lead = Lead.objects.filter(phone=caller_number).first()

        if not existing_lead:
            existing_lead = Lead.objects.create(
                name=f"Voxbay Caller - {caller_number}",
                phone=caller_number,
                source='VOXBAY CALL',
                status='ENQUIRY',
                assigned_to=agent
            )
        
        notes = f"Missed Call assigned by Admin\nCall UUID: {log.call_uuid}"
        
        lead_owner = existing_lead.assigned_to
        if not FollowUp.objects.filter(lead=existing_lead, status='pending', notes__contains=log.call_uuid).exists():
            FollowUp.objects.create(
                lead=existing_lead,
                assigned_to=agent,
                follow_up_date=timezone.now().date(),
                followup_type='call',
                status='pending',
                priority='high',
                notes=notes,
            )

        return Response({"message": "Successfully assigned"}, status=status.HTTP_200_OK)
