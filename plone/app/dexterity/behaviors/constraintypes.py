from AccessControl import ClassSecurityInfo
from AccessControl.class_init import InitializeClass
from Acquisition import aq_parent
from Acquisition import aq_inner
from z3c.form.interfaces import IAddForm
from z3c.form.interfaces import IEditForm
from zope import schema
from zope.component import adapts
from zope.interface import alsoProvides
from zope.interface import implements
from zope.schema.vocabulary import SimpleTerm
from zope.schema.vocabulary import SimpleVocabulary

# FIXME: new permission?
from Products.ATContentTypes import permission as ATCTPermissions
from Products.CMFCore.utils import getToolByName
from Products.CMFCore.PortalFolder import PortalFolderBase as PortalFolder
from Products.CMFPlone.interfaces import ISelectableConstrainTypes
from Products.CMFPlone.utils import base_hasattr
from plone.directives import form
from plone.dexterity.content import Container
from plone.dexterity.interfaces import IDexterityContainer
from plone.app.dexterity import MessageFactory as _


# constants for IConstrainTypes
ACQUIRE = -1 # acquire locally_allowed_types from parent
DISABLED = 0 # use default behavior of Container which uses the FTI information
             # (default)
ENABLED  = 1 # allow types from locally_allowed_types only

# Note: ACQUIRED means get allowable types from parent (regardless of
#  whether it supports IConstrainTypes) but only if parent is the same
#  portal_type (folder within folder). Otherwise, use the global_allow/default
#  behaviour (same as DISABLED).
constrain_types_modes = SimpleVocabulary([
    SimpleTerm(value=ACQUIRE, title=_(u'Acquire from parent')),
    SimpleTerm(value=DISABLED, title=_(u'Use default behavior from FTI')),
    SimpleTerm(value=ENABLED, title=_(u'Allow types from locally_allowed_types only'))
])


# Lifted from Products.ATContentTypes
def getParent(obj):
    portal_factory = getToolByName(obj, 'portal_factory', None)
    if portal_factory is not None and portal_factory.isTemporary(obj):
        # created by portal_factory
        parent = aq_parent(aq_parent(aq_parent(aq_inner(obj))))
    else:
        parent = aq_parent(aq_inner(obj))

    return parent


# Ditto
def parentPortalTypeEqual(obj):
    """Compares the portal type of obj to the portal type of its parent

    Return values:
        None - no acquisition context / parent available
        False - unequal
        True - equal
    """
    parent = getParent(obj)
    if parent is None:
        return None # no context
    parent_type = getattr(parent.aq_explicit, 'portal_type', None)
    obj_type = getattr(obj.aq_explicit, 'portal_type')
    if obj_type and parent_type == obj_type:
        return True
    return False


class IConstrainTypes(form.Schema):
    """Behavior interface to support restricting addable types.
    """

    form.fieldset('settings',
        label=u"Settings",
        fields=[
            'constrain_types_mode',
            'locally_allowed_types',
            'immediately_addable_types',
        ]
    )

    constrain_types_mode = schema.Choice(
        title=_(u'label_constrain_types_mode',
                default=u'Constrain types mode'),
        description=_(u'help_constrain_types_mode',
                      default=u'Select the constraint type mode for this '
                               'container.'),
        required=False,
        vocabulary=constrain_types_modes
    )
    form.omitted('constrain_types_mode')

    locally_allowed_types = schema.List(
        title=_(u'label_locally_allowed_types',
                default=u'Permitted types'),
        description=_(u'help_locally_allowed_types',
                      default=u'Select the types which will be addable inside '
                               'this container.'),
        required=False,
        unique=True,
        value_type=schema.TextLine(title=u"FTI")
    )
    form.omitted('locally_allowed_types')

    immediately_addable_types = schema.List(
        title=_(u'label_immediately_addable_types',
                default=u'Preferred types'),
        description=_(u'help_immediately_addable_types',
                      default=u'Select the types which will be addable '
                               'from the "Add new item" menu. Any '
                               'additional types set in the list above '
                               'will be addable from a separate form.'),
        required=False,
        unique=True,
        value_type=schema.TextLine(title=u"FTI")
    )
    form.omitted('immediately_addable_types')

alsoProvides(IConstrainTypes, form.IFormFieldProvider)


class ConstrainTypes(object):
    implements(IConstrainTypes, ISelectableConstrainTypes)
    adapts(IDexterityContainer)

    security = ClassSecurityInfo()

    def __init__(self, context):
        self.context = context


    security.declarePublic('getConstrainTypesMode')
    def getConstrainTypesMode(self):
        """
        Find out if add-restrictions are enabled. Returns 0 if they are
        disabled (the type's default FTI-set allowable types is in effect),
        1 if they are enabled (only a selected subset if allowed types will be
        available), and -1 if the allowed types should be acquired from the
        parent. Note that in this case, if the parent portal type is not the
        same as the portal type of this object, fall back on the default (same
        as 0)
        """
        if base_hasattr(self.context, 'constrain_types_mode'):
            return self.context.constrain_types_mode
        else:
            return self._getDefaultConstrainTypesMode()


    security.declarePublic('getLocallyAllowedTypes')
    def getLocallyAllowedTypes(self, context=None):
        """If constrain_types_mode is ENABLE, return the list of types
        set. If it is ACQUIRE, get the types set on the parent so long
        as the parent is of the same type - if not, use the same behaviuor as
        DISABLE: return the types allowable in the item.
        """
        if context is None:
            context = self.context
        mode = self.getConstrainTypesMode()

        if mode == DISABLED:
            return [
                fti.getId()
                for fti in self.getDefaultAddableTypes(context)
            ]
        elif mode == ENABLED:
            if base_hasattr(self.context, 'locally_allowed_types'):
                return self.context.locally_allowed_types
            else:
                return []
        elif mode == ACQUIRE:
            parent = getParent(self)
            if not parent:
                return [
                    fti.getId()
                    for fti in self.getDefaultAddableTypes(context)
                ]
            elif not parentPortalTypeEqual(self):
                # if parent.portal_type != self.portal_type:
                default_addable_types = [
                    fti.getId()
                    for fti in self.getDefaultAddableTypes(context)
                ]
                if ISelectableConstrainTypes.providedBy(parent):
                    return [
                        t
                        for t in parent.getLocallyAllowedTypes(context)
                        if t in default_addable_types
                    ]
                else:
                    return [
                        t for t in parent.getLocallyAllowedTypes()
                        if t in default_addable_types
                    ]
            else:
                if ISelectableConstrainTypes.providedBy(parent):
                    return parent.getLocallyAllowedTypes(context)
                else:
                    return parent.getLocallyAllowedTypes()
        else:
            raise ValueError, "Invalid value for constrain_types_mode"


    security.declarePublic('getImmediatelyAddableTypes')
    def getImmediatelyAddableTypes(self, context=None):
        """Get the list of type ids which should be immediately addable.
        If constrain_types_mode is ENABLE, return the list set; if it is
        ACQUIRE, use the value from the parent; if it is DISABLE, return
        all type ids allowable on the item.
        """
        if context is None:
            context = self.context
        mode = self.getConstrainTypesMode()

        if mode == DISABLED:
            return [
                fti.getId()
                for fti in self.getDefaultAddableTypes(context)
            ]
        elif mode == ENABLED:
            if base_hasattr(self.context, 'immediately_addable_types'):
                return self.context.immediately_addable_types
            else:
                return []
        elif mode == ACQUIRE:
            parent = getParent(self)
            if not parent:
                return [
                    fti.getId()
                    for fti in PortalFolder.allowedContentTypes(context)
                ]
            elif not parentPortalTypeEqual(self):
                default_allowed = [
                    fti.getId()
                    for fti in PortalFolder.allowedContentTypes(context)
                ]
                return [
                    t
                    for t in parent.getImmediatelyAddableTypes(context)
                    if t in default_allowed
                ]
            else:
                parent = aq_parent(aq_inner(self))
                return parent.getImmediatelyAddableTypes(context)
        else:
            raise ValueError, "Invalid value for constrain_types_mode"


    security.declarePublic('getDefaultAddableTypes')
    def getDefaultAddableTypes(self, context=None):
        """returns a list of normally allowed objects as ftis.
        Exactly like Container.allowedContentTypes except this
        will check in a specific context.
        """
        if context is None:
            context = self.context

        portal_types = getToolByName(self.context, 'portal_types')
        myType = portal_types.getTypeInfo(self)
        result = portal_types.listTypeInfo()
        # Don't give parameter context to portal_types.listTypeInfo().
        # If we do that, listTypeInfo will execute
        # t.isConstructionAllowed(context) for each content type
        # in portal_types.
        # The isConstructionAllowed should be done only on allowed types.
        if myType is not None:
            return [
                t
                for t in result
                if myType.allowType(t.getId()) and \
                   t.isConstructionAllowed(context)
            ]

        return [t for t in result if t.isConstructionAllowed(context)]


    security.declarePublic('allowedContentTypes')
    def allowedContentTypes(self, context=None):
        """returns constrained allowed types as list of fti's
        """
        if context is None:
            context = self.context
        mode = self.getConstrainTypesMode()

        # Short circuit if we are disabled or acquiring from non-compatible
        # parent

        parent = getParent(self)
        if mode == DISABLED or \
           (mode == ACQUIRE and not parent):
            return PortalFolder.allowedContentTypes(context)
        elif mode == ACQUIRE and not parentPortalTypeEqual(self):
            globalTypes = self.getDefaultAddableTypes(context)
            allowed = list(parent.getLocallyAllowedTypes())
            return [
                fti
                for fti in globalTypes
                if fti.getId() in allowed
            ]
        else:
            globalTypes = self.getDefaultAddableTypes(context)
            allowed = list(self.getLocallyAllowedTypes())
            ftis = [
                fti
                for fti in globalTypes
                if fti.getId() in allowed
            ]
            return ftis


    # Protected triggered problems in Script Python (setConstrainTypes.cpy)
    #security.declareProtected(ATCTPermissions.ModifyConstrainTypes, 'setConstrainTypesMode')
    security.declarePublic('setConstrainTypesMode')
    def setConstrainTypesMode(self, mode):
        """
        Set how addable types is controlled in this class. If mode is 0, use
        the type's default FTI-set allowable types). If mode is 1, use only
        those types explicitly enabled using setLocallyAllowedTypes(). If
        mode is -1, acquire the allowable types from the parent. If the parent
        portal type is not the same as this object's type, fall back on the
        behaviour obtained if mode == 0.
        """
        self.context.constrain_types_mode = mode


    # Protected triggered problems in Script Python (setConstrainTypes.cpy)
    #security.declareProtected(ATCTPermissions.ModifyConstrainTypes, 'setLocallyAllowedTypes')
    security.declarePublic('setLocallyAllowedTypes')
    def setLocallyAllowedTypes(self, types):
        """
        Set a list of type ids which should be allowed. This must be a
        subset of the type's FTI-set allowable types. This list only comes
        into effect when the restrictions mode is 1 (enabled).
        """
        self.context.locally_allowed_types = types


    # Protected triggered problems in Script Python (setConstrainTypes.cpy)
    #security.declareProtected(ATCTPermissions.ModifyConstrainTypes, 'setImmediatelyAddableTypes')
    security.declarePublic('setImmediatelyAddableTypes')
    def setImmediatelyAddableTypes(self, types):
        """
        Set the list of type ids which should be immediately/most easily
        addable. This list must be a subset of any types set in
        setLocallyAllowedTypes.
        """
        self.context.immediately_addable_types = types


    # Protected triggered problems in Script Python (setConstrainTypes.cpy)
    #security.declareProtected(ATCTPermissions.ModifyConstrainTypes, 'canSetConstrainTypes')
    security.declarePublic('canSetConstrainTypes')
    def canSetConstrainTypes(self):
        """
        Return True if the current user is permitted to constrain addable
        types in this container.
        """
        mtool = getToolByName(self.context, 'portal_membership')
        member = mtool.getAuthenticatedMember()
        # FIXME: upgrade step with new permission?
        return member.has_permission(ATCTPermissions.ModifyConstrainTypes,
                                     self.context)

    def _getDefaultConstrainTypesMode(self):
       """Configure constrainTypeMode depending on the parent

       ACQUIRE if parent support ISelectableConstrainTypes
       DISABLE if not
       """
       portal_factory = getToolByName(self.context, 'portal_factory', None)
       if portal_factory is not None and portal_factory.isTemporary(self):
           # created by portal_factory
           parent = aq_parent(aq_parent(aq_parent(aq_inner(self))))
       else:
           parent = aq_parent(aq_inner(self))

       if ISelectableConstrainTypes.providedBy(parent) and parentPortalTypeEqual(self):
           return ACQUIRE
       else:
           return DISABLED

InitializeClass(ConstrainTypes)
