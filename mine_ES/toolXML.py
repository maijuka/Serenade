import xml.dom.minidom
import pdb

BOOL_MAP = {'true': True, 'false': False, 't': True, 'f': False, '0': False, '0.0': False, '1': True, 0:False, 1:True, None: None}

def isElementNode(node):
    return node.nodeType == xml.dom.Node.ELEMENT_NODE

def tagName(node):
    return node.tagName

def children(node):
    return node.childNodes

def parseXML(filename):
    try:
        doc = xml.dom.minidom.parse(filename)
    except Exception as inst:
        doc = None
        print("File %s could not be read! (%s)" % (filename, inst))
    return doc

def getChildrenText(element):
    return getNodesText(element.childNodes)

def getNodesText(nodelist):
    rc = ""
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data
        if node.nodeType == node.CDATA_SECTION_NODE:
            rc = rc + node.data.strip("\"")
    return str(rc)
    # except UnicodeEncodeError as e:
    #     return  unicode(rc)

def parseToType(raw_value, value_type=None):
    if value_type is not None and type(raw_value) != value_type:
        try:
            if value_type is bool and raw_value in BOOL_MAP:
                return BOOL_MAP.get(raw_value)            
            raw_value = value_type(raw_value)
        except ValueError:
            raw_value = None
    return raw_value

def getTagData(node, tag, value_type=None):
    et = node.getElementsByTagName(tag)
    if len(et) == 0:
        return None
    return parseToType(getChildrenText(et[0]), value_type)

def getValue(element, value_type=None):
    return getTagData(element, "value", value_type)

def getValues(node, value_type=None, tag_name="value"):
    values = []
    for valuen in node.getElementsByTagName(tag_name):
        tmp = parseToType(getChildrenText(valuen), value_type)
        if tmp is not None:
            values.append(tmp)
    return values
