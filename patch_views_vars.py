with open('mailcenter/views.py', 'r', encoding='utf-8') as f:
    views = f.read()

endpoint = '''
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_template_variables(request):
    from .variables import VARIABLES
    import re
    vars_list = [{'id': v[0], 'label': v[1]} for v in VARIABLES]
    
    try:
        from trainers.models import ProcessingDynamicField
        for d in ProcessingDynamicField.objects.all():
            clean_k = re.sub(r'[^a-zA-Z0-9_]', '_', d.name.lower().strip())
            if clean_k not in [v['id'] for v in vars_list]:
                vars_list.append({'id': clean_k, 'label': d.name})
    except Exception:
        pass
        
    return Response(vars_list)

@api_view(['GET'])
'''

views = views.replace("@api_view(['GET'])", endpoint, 1)

with open('mailcenter/views.py', 'w', encoding='utf-8') as f:
    f.write(views)
