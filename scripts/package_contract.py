"""Exact sample-column contract, front-end SKU order, no original-price fallback."""
import re,json,html
def decode_detail_payload(content):
    """Decode JD description bytes without silently replacing text."""
    try:
        return content.decode('utf-8-sig')
    except UnicodeDecodeError:
        return content.decode('gb18030')

HEADERS=['*标题','货号','商品属性','类目','品牌','规格1','规格2','*价格','库存','短标题','商家SKU','SKU商品条形码','SKU属性','无理由退货','支付方式限制','产地','发货地','商品条形码','商品毛重(公斤)','[包装]长(mm)','[包装]宽(mm)','[包装]高(mm)']
def ordered_detail_urls(payload):
    m=re.match(r'\s*showdesc\((.*)\)\s*$',payload,re.S)
    if not m:raise ValueError('DETAIL_FORMAT_INVALID')
    content=html.unescape(str(json.loads(m.group(1)).get('content') or ''))
    pattern=r'(?:data-lazyload|src)\s*=\s*[\'\"]([^\'\"]+)[\'\"]|url\(\s*[\'\"]?([^\'\")]+?)\s*[\'\"]?\s*\)'
    out=[]
    for match in re.finditer(pattern,content,re.I):
        u=(match.group(1) or match.group(2)).strip()
        if u.startswith('//'):u='https:'+u
        # Merchant HTML sometimes nests a broken img tag whose data-lazyload value is
        # escaped markup (e.g. "http://<div><img style="). Only accept URLs with a
        # real hostname followed by a path separator.
        if not re.match(r'^https?://[A-Za-z0-9.-]+(?::\d+)?/',u):continue
        # Merchant HTML sometimes yields a host-only or directory-only URL (e.g.
        # https://img10.360buyimg.com/imgzone/) that the CDN answers with 405.
        if not re.search(r'\.(?:jpg|jpeg|png|webp)(?:\?|$)',u,re.I) and '/jfs/' not in u:continue
        if u not in out:out.append(u)
    return out

def table_matrix(main,variants,prices):
    attrs={x['labelName']:str(x.get('labelValue') or '') for x in main.get('attrs',[]) if x.get('labelName')}
    product_attrs=''.join(f'{k}:{v};' for k,v in attrs.items())
    matrix=[]
    for i,row in enumerate(variants):
        p=prices.get(row['sku'],{}).get('pp')
        if p is None or not re.fullmatch(r'\d+(?:\.\d+)?',str(p)) or float(p)<=0:raise ValueError('ARRIVAL_PRICE_MISSING')
        r=[None]*22
        if i==0:r[:5]=[main['title'],attrs.get('货号') or None,product_attrs,'>'.join(x['text'] for x in main.get('crumbs',[])[:3] if x.get('text')),attrs.get('品牌','')]
        r[5]=row['spec1'];r[6]=row['spec2'];r[7]=float(p);r[8]=999
        specific=prices[row['sku']].get('attrs') or main.get('attrs',[])
        r[12]=''.join(f"{x['labelName']}:{x.get('labelValue') or ''};" for x in specific if x.get('labelName'))
        matrix.append(r)
    return matrix


def error_state(error):
    return {'PRODUCT_UNAVAILABLE':'PRODUCT_UNAVAILABLE','ARRIVAL_PRICE_MISSING':'ARRIVAL_PRICE_PENDING','HTTP_403_REFUSED':'ACCESS_REFUSED'}.get(error.get('reason'),'PENDING')
