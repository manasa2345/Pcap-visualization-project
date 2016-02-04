from scapy.all import *
from datetime import datetime
import json
import sys
from models import Stat ,User, Packet, Session
from database import db_session,init_db
#from netaddr import IPNetwork, IPAddress

def hexdump(x):
    """Given a Raw string, return an ASCII string with "." instead of non recognised characters"""
    x = str(x)
    result = ""
    for i in range(len(x)):
        result += sane_color(x[i])
    return result

def initiate():
    """ Execute a drop_all() followed by a create_all() that clean the database"""
    init_db() 

def get_protocol(pkt):
    """Identified the protocol of a given packet"""
    protocol = "AUTRE"
    if pkt.haslayer(TCP):
        if pkt[TCP].dport == 7 or pkt[TCP].sport == 7:
            protocol = "ICMP"
        elif pkt[TCP].dport == 20 or pkt[TCP].sport == 20:
            protocol = "FTP"
        elif pkt[TCP].dport == 21 or pkt[TCP].sport == 21:
            protocol = "FTP"
        elif pkt[TCP].dport == 22 or pkt[TCP].sport == 22:
            protocol = "SSH"
        elif pkt[TCP].dport == 25 or pkt[TCP].sport == 25:
            protocol = "SMTP"
        elif pkt[TCP].dport == 80 or pkt[TCP].sport == 80:
            protocol = "HTTP"
        elif pkt[TCP].dport == 88 or pkt[TCP].sport == 88:
            protocol = "KERBEROS"
        elif pkt[TCP].dport == 110 or pkt[TCP].dport == 109 or pkt[TCP].sport == 110 or pkt[TCP].sport == 109:
            protocol = "POP3"
        elif pkt[TCP].dport == 115 or pkt[TCP].sport == 115:
            protocol = "SFTP"
        elif pkt[TCP].dport == 220 or pkt[TCP].dport == 143 or pkt[TCP].sport == 220 or pkt[TCP].sport == 143:
            protocol = "IMAP"
        elif pkt[TCP].dport == 389 or pkt[TCP].sport == 389:
            protocol = "LDAP"
        elif pkt[TCP].dport == 443 or pkt[TCP].sport == 443:
            protocol = "HTTPS"                
        elif pkt[TCP].dport == 445 or pkt[TCP].sport == 445:
            protocol = "SMB"
        elif pkt[TCP].dport == 636 or pkt[TCP].sport == 636:
            protocol = "LDAPS"
        elif pkt[TCP].dport == 993 or pkt[TCP].sport == 993:
            protocol = "IMAPS"
        elif pkt[TCP].dport == 995 or pkt[TCP].sport == 995:
            protocol = "POP3S"
        else:
            protocol = "TCP"
    elif pkt.haslayer(UDP):
        if pkt[UDP].dport == 53 or pkt[UDP].sport == 53:
            protocol = "DNS"
        elif pkt[UDP].dport == 5353 or pkt[UDP].sport == 5353:
            protocol = "MDNS"
        else:
            protocol = "UDP"
    elif pkt.haslayer(ARP):
        protocol = "ARP"
    elif pkt.haslayer(ICMP):
        protocol = "ICMP"

    return protocol

def feed_stats(stat, packet):
    """Create statistiques about protocols used, which will be added to the DB during add() execution"""
    protocol = get_protocol(packet)
    stat["TOTAL"] += 1
    if protocol in  stat:
        stat[protocol] += 1 
    else:
        stat[protocol] = 1  

def feed_trames(pkt,session):
    """Populate the Packet Table is the packet is involved in a recognised protocol only"""
    timestamp = datetime.fromtimestamp(pkt.time).strftime('%Y-%m-%d %H:%M:%S')
    protocol = get_protocol(pkt)
    data={}
    if protocol != "AUTRE":
        if pkt.haslayer(IP):
            ip = pkt.getlayer(IP) 
            hostSrc = ip.src
            hostDest = ip.dst

            if ip.haslayer(TCP):
                tcp = ip.getlayer(TCP)
                portSrc = tcp.sport
                portDest = tcp.dport
                
            elif ip.haslayer(UDP):
                udp = ip.getlayer(UDP)
                portSrc = udp.sport
                portDest = udp.dport
                
            else:
                portSrc=None
                portDest=None
                
        elif pkt.haslayer(ARP):
            arp = pkt.getlayer(ARP)
            hostSrc = arp.psrc
            hostDest = arp.pdst  
            portSrc = None
            portDest = None
       
        if pkt.haslayer(Raw):
            data = {"data" : hexdump(pkt.getlayer(Raw))}
        
        P = Packet(hostSrc,hostDest,portSrc,portDest,protocol,data,timestamp,session)
        db_session.add(P)

def extract_session(summary,data):
    """Populate the Packet Table is the session is TCP or UDP protocol only"""
    s = summary.split(' ')
    # summary est de la forme UDP 192.168.11.228:21893 > 208.67.222.222:
    if s[0] == "TCP" or s[0] == "UDP":
        Src = s[1].split(":")
        Dst = s[3].split(":")
        hostSrc = Src[0]
        portSrc = Src[1]
        hostDest = Dst[0]
        portDest = Dst[1]
        protocol = s[0]
        if hostDest != "255.255.255.255":
            sess = Session(hostSrc,hostDest,portSrc,portDest,protocol) 
            db_session.add(sess) 
            for pkt in data:
                feed_trames(pkt,sess)

def feed_user(user,pkt):
    """Create a dictionnary of the users, which will be added to the DB during add() execution"""
    if pkt.haslayer(IP):
        ip = pkt.getlayer(IP) 
        length = len(pkt)
        # length = sys.getsizeof(ip)
        protocol = get_protocol(ip)
        if ip.src in user:
            user[ip.src]["Volume"] += length
            if protocol in user[ip.src]["Protocole"]:
                user[ip.src]["Protocole"][protocol]["Volumeout"] += length
                user[ip.src]["Protocole"][protocol]["Nombreout"] += 1
            else:
                user[ip.src]["Protocole"][protocol] = {
                    "Volumein": 0,
                    "Volumeout": length,
                    "Nombrein": 0,
                    "Nombreout": 1                      
                }
        else:
            user[ip.src]={
                "Volume": length,
                "Protocole":
                  {
                      protocol:
                      {
                        "Volumein": 0,
                        "Volumeout": length,
                        "Nombrein": 0,
                        "Nombreout": 1
                      }
                  }
            }

        if ip.dst in user:
            user[ip.dst]["Volume"] += length

            if protocol in user[ip.dst]["Protocole"]:
                user[ip.dst]["Protocole"][protocol]["Volumein"] += length
                user[ip.dst]["Protocole"][protocol]["Nombrein"] += 1
            
            else:
                user[ip.dst]["Protocole"][protocol] = {
                    "Volumein": length,
                    "Volumeout": 0,
                    "Nombrein": 1,
                    "Nombreout": 0
                }
        else:
            user[ip.dst] ={
                "Volume": length,
                "Protocole":
                  {
                      protocol:
                      {
                        "Volumein": length,
                        "Volumeout":0,
                        "Nombrein":1,
                        "Nombreout":0
                      }
                  }
            }
    
def add(user,stat):
    """Add the users and the stats in the session."""
    for el in user:
        U = User(el,user[el])
        db_session.add(U)
    
    for el in stat:
        S = Stat(el,stat[el])
        db_session.add(S)

def parse(filename):
    """ Parses pcap file and populate de PostgreSQL Database. Populates User, Session, Stat and Packet Tables"""

    t0 = 0; t1 = 0; t2 = 0; t3 = 0; t4 = 0
    user = {}
    stat = { "TOTAL" : 0 }
    mailpkts=[]
    result = ""
    try:
        initiate()
    except Exception as e:
        print e
    
    tread = time.clock()
    pcap = rdpcap(filename)
    
    print "Pcap file has been read : " + str(time.clock() - tread)
    
    for pkt in pcap:
        t0 = time.clock()
        feed_user(user,pkt)
        t1 += time.clock() - t0
        t0 = time.clock()
        feed_stats(stat,pkt)
        t2 += time.clock()-t0
    print result
    add(user,stat)
    
    print "Treemap Table generated : " + str(t1) + " seconds"
    print "Stat Table generated : "+ str(t2) + " seconds"

    t0 = time.clock()
    s = pcap.sessions()
    
    for summary,data in s.iteritems():
        extract_session(summary,data)
    t3 += time.clock() - t0    

    print "Sessions and Packets Tables generated : " + str(t3) + " seconds"
    
    t0 = time.clock()
    db_session.commit()
    t4 += time.clock()-t0
    
    print "Commit in PostGreSQL done : " + str(t4) + " seconds"
    print stat 
    return {}

#-----------------------------------UNUSED FUNCTION-----------------------------------------#

# def get_web(filename):
#     webpkts = []
#     result = ""
#     pcap = rdpcap(filename)
#     for packet in pcap:
#         if TCP in packet:
#             if packet.getlayer('TCP').dport == 80 or packet.getlayer('TCP').dport == 8080:
#                 webpkts.append(packet)
#     for packet in webpkts:
#         if packet.getlayer('TCP').flags == 24:
#             result = result + '''<div class="ui vertical segment"><p>'''
#             result = result + packet.getlayer('Raw').load.replace(' ','&nbsp;').replace('\n','<br/>')
#             result = result + '''</p></div>'''
#     if result == "":
#         result = '''<div class="ui vertical segment"><p>No WebView Packets!</p></div>'''
#     result = re.compile('[\\x00-\\x08\\x0b-\\x0c\\x0e-\\x1f\\x80-\\xff]').sub('', result)
#     return result

# def get_mail(filename):
#     mailpkts = []
#     result = "<p>"
#     pcap = rdpcap(filename)
#     for packet in pcap:
#         if TCP in packet:
#             if packet.getlayer('TCP').dport == 110 or packet.getlayer('TCP').sport == 110 or packet.getlayer('TCP').dport == 143 or packet.getlayer('TCP').sport == 143 :
#                 mailpkts.append(packet)
#     for packet in mailpkts:
#         if packet.getlayer('TCP').flags == 24:
#             result = result + packet.getlayer('Raw').load.replace(' ','&nbsp;').replace('\n','<br/>')
#     if result == "<p>":
#         result = result + "No Mail Packets!"
#     result = result + "</p>"
#     result = re.compile('[\\x00-\\x08\\x0b-\\x0c\\x0e-\\x1f\\x80-\\xff]').sub('', result)
#     return result

# def in_network(ip,network = "192.168.0.0/16"):

#     if IPAddress(ip) in IPNetwork(network):
#         return True
#     else:
#         return False