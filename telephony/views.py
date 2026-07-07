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
    from leads.models import Lead, FollowUp
    from accounts.models import User
    from django.utils import timezone

    if obj.call_type == 'outgoing':
        lead_number = obj.destination
        agent_phone = obj.extension
        direction_text = "Outgoing"
    else:
        lead_number = obj.caller_number
        agent_phone = obj.agent_number
        direction_text = "Incoming"

    if not lead_number:
        return

    agent_user = None
    if agent_phone:
        agent_user = User.objects.filter(Q(voxbay_number=agent_phone) | Q(voxbay_extension=agent_phone)).first()

    existing_lead = Lead.objects.filter(phone=lead_number).first()

    if obj.call_status in ['ANSWER', 'ANSWERED']:
        if not existing_lead and agent_user:
            existing_lead = Lead.objects.create(
                name=f"Voxbay Caller - {lead_number}",
                phone=lead_number,
                source='VOXBAY CALL',
                status='ENQUIRY',
                assigned_to=agent_user
            )

        if existing_lead and agent_user:
            duration_str = str(obj.duration) + 's' if obj.duration else 'Unknown'
            notes = f"Answered {direction_text} Call\nDuration: {duration_str}\n"
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
            answered_exists = VoxbayCallLog.objects.filter(call_uuid=obj.call_uuid, call_status__in=['ANSWER', 'ANSWERED']).exists()
            if not answered_exists:
                notes = f"Missed {direction_text} Call from Lead\nCall UUID: {obj.call_uuid}" if direction_text == "Incoming" else f"Unanswered {direction_text} Call to Lead\nCall UUID: {obj.call_uuid}"
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

    def get(self, request):
        return self.post(request)

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
            
        direction_payload = data.get("direction") or data.get("callType") or data.get("type")
        if direction_payload and isinstance(direction_payload, str) and direction_payload.lower() in ["incoming", "outgoing"]:
            call_type = direction_payload.lower()
        elif data.get("callerNumber") or data.get("caller_number") or data.get("callernumber") or (data.get("callerid") and not data.get("destination")):
            call_type = "incoming"
        elif data.get("destination") or data.get("calledNumber"):
            call_type = "outgoing"
        else:
            call_type = "incoming"

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
        
        duration_val = _safe_int(
            data.get("totalCallDuration") or data.get("duration") or data.get("callDuration") or data.get("billsec")
        )

        raw_status = data.get("callStatus") or data.get("status")
        if not raw_status and duration_val and duration_val > 0:
            raw_status = "ANSWERED"
        elif not raw_status:
            raw_status = "MISSED"

        _set("call_type",             call_type)
        _set("call_status",           raw_status)
        _set("duration",              duration_val)
        _set("conversation_duration", _safe_int(data.get("conversationDuration")))
        _set("recording_url",         _resolve_recording_url(
                                          data.get("recording_URL") or data.get("recording_url") or data.get("recordingUrl") or data.get("callRecordingUrl") or data.get("audio")
                                      ))
        if call_start:
            defaults["call_start"] = call_start
        if call_end:
            defaults["call_end"] = call_end

        if call_type == "incoming":
            _set("called_number",      data.get("calledNumber"))
            _set("caller_number",      data.get("callerNumber") or data.get("callerid") or data.get("caller_number") or data.get("phone") or data.get("number"))
            _set("agent_number",       data.get("AgentNumber") or data.get("agentNumber") or data.get("extension"))
            _set("dtmf",               data.get("dtmf"))
            _set("transferred_number", data.get("transferredNumber"))
        else:
            _set("extension",     data.get("extension") or data.get("agentNumber") or data.get("AgentNumber"))
            _set("destination",   data.get("destination") or data.get("calledNumber") or data.get("phone") or data.get("number"))
            _set("caller_id",     data.get("callerid"))
            _set("caller_number", data.get("callerid"))

        callevent = data.get("Callevent") or data.get("callevent") or data.get("event") or ""

        if call_uuid:
            obj, created = VoxbayCallLog.objects.update_or_create(
                call_uuid=call_uuid,
                defaults=defaults,
            )
            logger.info(
                f"[Voxbay Webhook] {'created' if created else 'updated'} "
                f"CallLog id={obj.id} uuid={call_uuid} event={callevent}"
            )
            
            # Skip timeline updates for intermediate events; wait for CDR
            if callevent.strip().lower() not in ["call start", "start", "connect", "ringing", "disconnect"]:
                try:
                    process_voxbay_call_log(obj)
                except Exception as e:
                    logger.error(f"[Voxbay] Error processing call log for lead generation: {e}")
            else:
                logger.info(f"[Voxbay Webhook] Skipped timeline generation for intermediate event: {callevent}")
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
                voxbay_extension = getattr(request.user, 'voxbay_extension', None)
                agent_numbers = []
                if voxbay_number:
                    agent_numbers.append(voxbay_number)
                if voxbay_extension:
                    agent_numbers.append(voxbay_extension)
                
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
                voxbay_number = getattr(request.user, 'voxbay_number', None)
                voxbay_extension = getattr(request.user, 'voxbay_extension', None)
                agent_numbers = []
                if user_phone:
                    base_phone = user_phone[-10:] if len(user_phone) >= 10 else user_phone
                    agents = VoxbayAgent.objects.filter(phone_number__endswith=base_phone)
                    agent_numbers = list(agents.values_list('phone_number', flat=True))
                    agent_numbers.extend([e for e in agents.values_list('extension', flat=True) if e])
                if voxbay_number and voxbay_number not in agent_numbers:
                    agent_numbers.append(voxbay_number)
                if voxbay_extension and voxbay_extension not in agent_numbers:
                    agent_numbers.append(voxbay_extension)
                
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
        
        voxbay_extension = request.user.voxbay_extension
        if not voxbay_extension:
            return Response(
                {"error": "Your Voxbay extension is not configured. Please contact an admin."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        voxbay_uid = getattr(settings, 'VOXBAY_UID', None)
        voxbay_upin = getattr(settings, 'VOXBAY_UPIN', None)
        
        if not voxbay_uid or not voxbay_upin:
            logger.error("[Click-to-Call] VOXBAY_UID or VOXBAY_UPIN missing from settings")
            return Response(
                {"error": "Server configuration error: Voxbay credentials not set"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# ─── Call Agent Stats ─────────────────────────────────────────────────────────

from accounts.models import User

class CallAgentStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not has_dynamic_permission(request.user, 'voxbay:admin'):
            return Response({"error": "Admin access required"}, status=403)
            
        qs = VoxbayCallLog.objects.all()
        qs = _date_filter(qs, request)

        call_type = request.query_params.get("call_type")
        if call_type in ("incoming", "outgoing"):
            qs = qs.filter(call_type=call_type)
            
        logs = qs.values(
            'call_type', 'call_status', 'agent_number', 'extension', 'conversation_duration'
        )
        
        valid_roles = ['ADM_MANAGER', 'ADM_COUNSELLOR', 'FLAG_COORDINATOR']
        users = User.objects.filter(is_active=True, db_roles__name__in=valid_roles).distinct()

        agents_map = {}
        user_by_incoming = {}
        user_by_outgoing = {}

        for u in users:
            uid = str(u.id)
            name = f"{u.first_name} {u.last_name}".strip() or u.username
            agents_map[uid] = {
                'identifier': uid,
                'agent_name': name,
                'incoming_calls_received': 0,
                'incoming_calls_answered': 0,
                'incoming_duration_total': 0,
                'outgoing_calls_made': 0,
                'outgoing_calls_answered': 0,
                'outgoing_duration_total': 0,
                'total_cancelled_missed': 0,
            }
            if u.voxbay_number:
                user_by_incoming[u.voxbay_number] = uid
            if u.voxbay_extension:
                user_by_outgoing[u.voxbay_extension] = uid
        
        overall = {
            'identifier': 'OVERALL_SYSTEM',
            'agent_name': 'OVERALL SYSTEM',
            'incoming_calls_received': 0,
            'incoming_calls_answered': 0,
            'incoming_duration_total': 0,
            'outgoing_calls_made': 0,
            'outgoing_calls_answered': 0,
            'outgoing_duration_total': 0,
            'total_cancelled_missed': 0,
        }

        for log in logs:
            ctype = log['call_type']
            status = log['call_status']
            dur = log['conversation_duration'] or 0
            
            # Determine agent identifier for this log based on active users in roles
            agent_id = None
            if ctype == 'incoming':
                agent_id = user_by_incoming.get(log['agent_number'])
            elif ctype == 'outgoing':
                agent_id = user_by_outgoing.get(log['extension'])
            
            # We process 'overall' unconditionally
            if ctype == 'incoming':
                overall['incoming_calls_received'] += 1
                if status == 'ANSWERED':
                    overall['incoming_calls_answered'] += 1
                    overall['incoming_duration_total'] += dur
                elif status in ['MISSED', 'NOANSWER', 'CANCEL']:
                    overall['total_cancelled_missed'] += 1
            elif ctype == 'outgoing':
                overall['outgoing_calls_made'] += 1
                if status == 'ANSWERED':
                    overall['outgoing_calls_answered'] += 1
                    overall['outgoing_duration_total'] += dur
                elif status in ['MISSED', 'NOANSWER', 'CANCEL']:
                    overall['total_cancelled_missed'] += 1

            if agent_id and agent_id in agents_map:
                ad = agents_map[agent_id]
                if ctype == 'incoming':
                    ad['incoming_calls_received'] += 1
                    if status == 'ANSWERED':
                        ad['incoming_calls_answered'] += 1
                        ad['incoming_duration_total'] += dur
                    elif status in ['MISSED', 'NOANSWER', 'CANCEL']:
                        ad['total_cancelled_missed'] += 1
                elif ctype == 'outgoing':
                    ad['outgoing_calls_made'] += 1
                    if status == 'ANSWERED':
                        ad['outgoing_calls_answered'] += 1
                        ad['outgoing_duration_total'] += dur
                    elif status in ['MISSED', 'NOANSWER', 'CANCEL']:
                        ad['total_cancelled_missed'] += 1
                        
        def compute_avgs(d):
            d['incoming_avg_duration'] = round(d['incoming_duration_total'] / d['incoming_calls_answered'], 1) if d['incoming_calls_answered'] else 0
            d['outgoing_avg_duration'] = round(d['outgoing_duration_total'] / d['outgoing_calls_answered'], 1) if d['outgoing_calls_answered'] else 0
            return d
            
        compute_avgs(overall)
        
        agent_results = []
        for k, v in agents_map.items():
            compute_avgs(v)
            agent_results.append(v)
            
        agent_results.sort(key=lambda x: (x['incoming_calls_answered'] + x['outgoing_calls_answered']), reverse=True)
        
        return Response({
            "overall_system": overall,
            "agents": agent_results
        })

        params = {
            "id_dept":     0,
            "uid":         voxbay_uid,
            "upin":        voxbay_upin,
            "user_no":     voxbay_extension,
            "destination": validated["destination"],
            "callerid":    voxbay_extension,
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
        missed_logs = VoxbayCallLog.objects.filter(call_type='incoming').exclude(call_status__in=['ANSWER', 'ANSWERED'])
        missed_logs = _date_filter(missed_logs, request)
        
        # Get all CallUUIDs that HAVE been answered
        answered_uuids = VoxbayCallLog.objects.filter(call_type='incoming', call_status__in=['ANSWER', 'ANSWERED']).values_list('call_uuid', flat=True)
        
        # Exclude those that were eventually answered
        unique_missed = missed_logs.exclude(call_uuid__in=answered_uuids).order_by('-created_at')

        # To avoid showing the same caller multiple times if they called repeatedly:
        # We group by caller_number (or call_uuid as fallback) and return the latest
        unique_missed_dict = {}
        for log in unique_missed:
            key = log.caller_number or log.call_uuid
            if key and key not in unique_missed_dict:
                unique_missed_dict[key] = log

        logs_to_check = list(unique_missed_dict.values())
        logs_to_return = []
        
        if logs_to_check:
            from leads.models import Lead
            caller_numbers = [log.caller_number for log in logs_to_check if log.caller_number]
            assigned_lead_phones = set(Lead.objects.filter(
                phone__in=caller_numbers,
                assigned_to__isnull=False
            ).values_list('phone', flat=True))
            
            for log in logs_to_check:
                if log.caller_number and log.caller_number in assigned_lead_phones:
                    continue
                logs_to_return.append(log)

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
        remarks_text = "assigned from missed"

        if not existing_lead:
            existing_lead = Lead.objects.create(
                name=f"Voxbay Caller - {caller_number}",
                phone=caller_number,
                source='VOXBAY CALL',
                status='ENQUIRY',
                assigned_to=agent,
                remarks=remarks_text
            )
        else:
            existing_lead.assigned_to = agent
            if existing_lead.remarks:
                if remarks_text not in existing_lead.remarks:
                    existing_lead.remarks = f"{existing_lead.remarks} | {remarks_text}"
            else:
                existing_lead.remarks = remarks_text
            existing_lead.save()
        
        assigner_name = request.user.get_full_name() or request.user.username
        notes = f"Missed Call assigned by {assigner_name}\nCall UUID: {log.call_uuid}"
        
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
