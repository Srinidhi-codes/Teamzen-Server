import re

def parse_user_agent(user_agent_string):
    """
    Parses a User-Agent string to return OS, browser, device type, and device name.
    Avoids external dependencies.
    """
    if not user_agent_string:
        return {
            'browser': 'Unknown Browser',
            'os': 'Unknown OS',
            'device_type': 'Unknown',
            'device_name': 'Unknown Device'
        }
    
    ua = user_agent_string.lower()
    
    # OS & Device Type & Device Name Detection
    if 'android' in ua:
        os = 'Android'
        device_type = 'Mobile'
        # Try to parse android device model name
        match = re.search(r'android\s+[^;]+;\s+([^;)]+)', user_agent_string, re.IGNORECASE)
        if not match:
            # Fallback patterns
            match = re.search(r'\(([^;]+);[^;]+Build', user_agent_string)
        device_name = match.group(1).strip() if match else 'Android Device'
    elif 'iphone' in ua:
        os = 'iOS'
        device_type = 'Mobile'
        device_name = 'iPhone'
    elif 'ipad' in ua:
        os = 'iOS'
        device_type = 'Tablet'
        device_name = 'iPad'
    elif 'windows phone' in ua:
        os = 'Windows Phone'
        device_type = 'Mobile'
        device_name = 'Windows Phone'
    elif 'macintosh' in ua or 'mac os x' in ua:
        os = 'macOS'
        device_type = 'Desktop'
        device_name = 'Mac'
    elif 'windows' in ua:
        os = 'Windows'
        device_type = 'Desktop'
        device_name = 'Windows PC'
    elif 'linux' in ua:
        os = 'Linux'
        device_type = 'Desktop'
        device_name = 'Linux PC'
    else:
        os = 'Unknown OS'
        device_type = 'Unknown'
        device_name = 'Unknown Device'
        
    # Browser Detection
    if 'edg/' in ua:
        browser = 'Edge'
    elif 'chrome' in ua or 'crios' in ua:
        # Note: Chrome user-agent string also contains Safari by spec, so we check Chrome first
        browser = 'Chrome'
    elif 'firefox' in ua or 'fxios' in ua:
        browser = 'Firefox'
    elif 'safari' in ua and 'chrome' not in ua:
        browser = 'Safari'
    elif 'opr/' in ua or 'opera' in ua:
        browser = 'Opera'
    else:
        browser = 'Unknown Browser'
        
    return {
        'browser': browser,
        'os': os,
        'device_type': device_type,
        'device_name': device_name
    }


def create_user_session(user, refresh_token, request, location=None):
    """
    Parses request user-agent and IP to create an active UserDeviceSession.
    Embeds refresh token's jti.
    Pass location to skip a second reverse-geocode lookup.
    """
    from users.models import UserDeviceSession
    from users.views import get_client_ip, get_location_from_ip
    
    try:
        jti = refresh_token['jti']
        ip = get_client_ip(request)
        ua_string = request.META.get('HTTP_USER_AGENT', '')
        parsed_ua = parse_user_agent(ua_string)
        
        # Coordinates (optional)
        latitude = None
        longitude = None
        if request and hasattr(request, 'data') and isinstance(request.data, dict):
            latitude = request.data.get('latitude')
            longitude = request.data.get('longitude')
            
        location = get_location_from_ip(ip, lat=latitude, lon=longitude) if location is None else location
        
        return UserDeviceSession.objects.create(
            user=user,
            jti=jti,
            ip_address=ip,
            user_agent=ua_string,
            location=location,
            browser=parsed_ua['browser'],
            os=parsed_ua['os'],
            device_type=parsed_ua['device_type'],
            device_name=parsed_ua['device_name'],
            is_active=True
        )
    except Exception as e:
        print(f"Error creating user device session: {e}")
        return None
