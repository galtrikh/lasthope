from core.models import FooterInfo

def footer_info(request):
    return {
        'footer_info': FooterInfo.objects.all()
    }