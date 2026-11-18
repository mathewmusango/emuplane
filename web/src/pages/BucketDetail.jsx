import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import Alert from '@cloudscape-design/components/alert'
import Box from '@cloudscape-design/components/box'
import Button from '@cloudscape-design/components/button'
import ButtonDropdown from '@cloudscape-design/components/button-dropdown'
import Checkbox from '@cloudscape-design/components/checkbox'
import ColumnLayout from '@cloudscape-design/components/column-layout'
import Container from '@cloudscape-design/components/container'
import ContentLayout from '@cloudscape-design/components/content-layout'
import FileUpload from '@cloudscape-design/components/file-upload'
import Header from '@cloudscape-design/components/header'
import Input from '@cloudscape-design/components/input'
import Modal from '@cloudscape-design/components/modal'
import RadioGroup from '@cloudscape-design/components/radio-group'
import Select from '@cloudscape-design/components/select'
import Textarea from '@cloudscape-design/components/textarea'
import Toggle from '@cloudscape-design/components/toggle'
import SpaceBetween from '@cloudscape-design/components/space-between'
import StatusIndicator from '@cloudscape-design/components/status-indicator'
import Table from '@cloudscape-design/components/table'
import Tabs from '@cloudscape-design/components/tabs'
import { api } from '../api'
import { useSession } from '../context'
import { regionName } from '../regionNames'
import { Shell } from '../components/Shell'

// One bucket: its own page with only the tabs this instance can back (no Metrics, Management, File systems, Access Points, Metadata).

// One file per request, the same ceiling the control enforces; larger files go up in parts.
const MAX_UPLOAD = 25 * 1024 * 1024
const MULTIPART_ABOVE = 8 * 1024 * 1024
const PART_SIZE = 5 * 1024 * 1024
const MAX_FILE = 200 * 1024 * 1024

const RETENTION_MODES = [
  { label: 'Governance', value: 'GOVERNANCE' },
  { label: 'Compliance', value: 'COMPLIANCE' },
]

const LEGAL_HOLD_OPTIONS = [
  { label: 'On', value: 'ON' },
  { label: 'Off', value: 'OFF' },
]

const dash = '\u2014'


// The console's three encryption choices, as the create page offers them.
const ENCRYPTION = [
  ['AES256', 'Amazon S3 managed keys (SSE-S3)'],
  ['aws:kms', 'AWS Key Management Service keys (SSE-KMS)'],
  ['aws:kms:dsse', 'Dual-layer server-side encryption (DSSE-KMS)'],
]

// The storage classes a rewrite may name; the control validates the same set.
const STORAGE_CLASSES = [
  ['STANDARD', 'Standard'],
  ['REDUCED_REDUNDANCY', 'Reduced redundancy'],
  ['STANDARD_IA', 'Standard-IA'],
  ['ONEZONE_IA', 'One Zone-IA'],
  ['INTELLIGENT_TIERING', 'Intelligent-Tiering'],
  ['GLACIER_IR', 'Glacier Instant Retrieval'],
  ['GLACIER', 'Glacier Flexible Retrieval'],
  ['DEEP_ARCHIVE', 'Glacier Deep Archive'],
  ['OUTPOSTS', 'Outposts'],
]

const OBJECT_ACLS = [
  ['private', 'Private'],
  ['public-read', 'Public read'],
]

// The bucket picker's options for a copy: every bucket the account has, each with the region it lives in.

const formatSize = (bytes) => {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
}

export default function BucketDetail() {
  const { name = '' } = useParams()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { account, region: sessionRegion } = useSession()

  // The URL's region may be missing or wrong, so HeadBucket answers where the bucket really is and the page reads nothing until it does.
  const requested = searchParams.get('region') || sessionRegion
  const requestedKey = searchParams.get('key')
  // The folder lives in the address bar, so the breadcrumb, a new tab and the back button all agree.
  const prefix = searchParams.get('prefix') || ''
  const [bucketRegion, setBucketRegion] = useState('')
  const [headMissing, setHeadMissing] = useState(false)
  const region = bucketRegion || requested

  const [objects, setObjects] = useState([])
  const [nextToken, setNextToken] = useState('')
  const [moreLoading, setMoreLoading] = useState(false)
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [newKey, setNewKey] = useState('')
  const [newBody, setNewBody] = useState('')
  const [file, setFile] = useState([])
  const [uploadError, setUploadError] = useState('')
  const [saving, setSaving] = useState(false)
  const [versioningEdit, setVersioningEdit] = useState(null)
  const [encryptionEdit, setEncryptionEdit] = useState(null)
  const [bucketKeyEdit, setBucketKeyEdit] = useState(false)
  const [tagEdit, setTagEdit] = useState(null)
  const [accessEdit, setAccessEdit] = useState(null)
  const [settings, setSettings] = useState(null)
  const [settingsError, setSettingsError] = useState('')
  const [documents, setDocuments] = useState({})
  const [editable, setEditable] = useState({})
  const [documentsError, setDocumentsError] = useState('')
  const [documentEdit, setDocumentEdit] = useState(null)
  const [documentError, setDocumentError] = useState('')
  const [objectView, setObjectView] = useState(null)
  const [objectError, setObjectError] = useState('')
  const [objectMeta, setObjectMeta] = useState(null)
  const [objectMetaError, setObjectMetaError] = useState('')
  const [uploadId, setUploadId] = useState('')
  const [uploadStatus, setUploadStatus] = useState('')
  const [objectTagEdit, setObjectTagEdit] = useState(null)
  const [objectTagError, setObjectTagError] = useState('')
  const [objectTagSaving, setObjectTagSaving] = useState(false)
  const [annotationEdit, setAnnotationEdit] = useState(null)
  const [annotationSaveError, setAnnotationSaveError] = useState('')
  const [annotationSaving, setAnnotationSaving] = useState(false)
  const [retentionEdit, setRetentionEdit] = useState(null)
  const [retentionError, setRetentionError] = useState('')
  const [legalHoldEdit, setLegalHoldEdit] = useState(null)
  const [legalHoldError, setLegalHoldError] = useState('')
  const [lockSaving, setLockSaving] = useState(false)
  const [annotation, setAnnotation] = useState(null)
  const [annotationError, setAnnotationError] = useState('')
  const [deletingObject, setDeletingObject] = useState(null)
  const [copying, setCopying] = useState(null)
  const [rewriting, setRewriting] = useState(null)
  const [aclChange, setAclChange] = useState(null)
  const [actionError, setActionError] = useState('')
  const [copyTo, setCopyTo] = useState(null)
  const [copyKey, setCopyKey] = useState('')
  const [copyError, setCopyError] = useState('')
  const [selected, setSelected] = useState([])
  const [copyMode, setCopyMode] = useState('copy')
  const [folderOpen, setFolderOpen] = useState(false)
  const [folderName, setFolderName] = useState('')
  const [notice, setNotice] = useState('')
  const [acting, setActing] = useState(false)
  const [allBuckets, setAllBuckets] = useState([])
  const [files, setFiles] = useState([])
  const [filesError, setFilesError] = useState('')
  const [points, setPoints] = useState([])
  const [pointsError, setPointsError] = useState('')
  const [tab, setTab] = useState('objects')
  const [versions, setVersions] = useState([])
  const [versionsError, setVersionsError] = useState('')
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [deletingVersion, setDeletingVersion] = useState(null)
  const [uploads, setUploads] = useState([])
  const [uploadsError, setUploadsError] = useState('')
  const [uploadsLoading, setUploadsLoading] = useState(false)
  const [uploadView, setUploadView] = useState(null)
  const [parts, setParts] = useState([])
  const [partsError, setPartsError] = useState('')
  const [partsLoading, setPartsLoading] = useState(false)
  const [aclRead, setAclRead] = useState(null)
  const [aclReadError, setAclReadError] = useState('')
  const [aclReadLoading, setAclReadLoading] = useState(false)
  const [aclSaved, setAclSaved] = useState('')
  const [aclVersions, setAclVersions] = useState([])
  const [aclVersionsError, setAclVersionsError] = useState('')
  const [aclVersion, setAclVersion] = useState('')
  const [ownershipEdit, setOwnershipEdit] = useState(null)
  const [versionsNext, setVersionsNext] = useState(null)
  const [versionsMore, setVersionsMore] = useState(false)
  const [uploadsNext, setUploadsNext] = useState(null)
  const [uploadsMore, setUploadsMore] = useState(false)
  const [partsNext, setPartsNext] = useState(null)
  const [partsMore, setPartsMore] = useState(false)

  // A different folder is a different list: the filter and the selection belong to the one you left.
  useEffect(() => {
    setFilter('')
    setSelected([])
  }, [prefix])

  useEffect(() => {
    if (!account || !name) return undefined
    let live = true
    api
      .headBucket(account, requested, name)
      .then((answer) => {
        if (!live) return
        if (!answer?.ok) {
          setBucketRegion(requested)
          return
        }
        setHeadMissing(!answer.exists)
        setBucketRegion(answer.region || requested)
      })
      .catch(() => {
        // A head that fails leaves the page where the URL pointed; the list below reports the real problem.
        if (live) setBucketRegion(requested)
      })
    return () => {
      live = false
    }
  }, [account, requested, name])

  // The address bar follows the bucket, so the link is right the next time; the folder and the object stay in it.
  useEffect(() => {
    if (!bucketRegion || bucketRegion === requested) return
    setSearchParams(
      (held) => {
        const next = new URLSearchParams(held)
        next.set('region', bucketRegion)
        return next
      },
      { replace: true },
    )
  }, [bucketRegion, requested, setSearchParams])

  const loadObjects = useCallback(async () => {
    if (!account || !bucketRegion || headMissing) return
    setLoading(true)
    try {
      const payload = await api.s3Objects(account, region, name, prefix)
      setObjects(payload.objects || [])
      setNextToken(payload.next_token || '')
      setError('')
    } catch (err) {
      setObjects([])
      setNextToken('')
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [account, region, name, prefix, bucketRegion, headMissing])

  useEffect(() => {
    loadObjects()
  }, [loadObjects])

  // One listing is one page of keys, so a folder with more than that is continued rather than shown short.
  const loadMore = async () => {
    if (!nextToken) return
    setMoreLoading(true)
    try {
      const payload = await api.s3Objects(account, region, name, prefix, nextToken)
      setObjects((held) => [...held, ...(payload.objects || [])])
      setNextToken(payload.next_token || '')
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setMoreLoading(false)
    }
  }

  useEffect(() => {
    if (!account || !bucketRegion || headMissing) return undefined
    let live = true
    api
      .bucketSettings(account, region, name)
      .then((answer) => {
        if (!live) return
        setSettings(answer.settings || null)
        setSettingsError('')
      })
      .catch((err) => {
        if (live) setSettingsError(err.message)
      })
    return () => {
      live = false
    }
  }, [account, region, name, bucketRegion, headMissing])

  const uploadMultipart = async (chosen, key) => {
    const created = await api.createMultipartUpload({
      account,
      region,
      bucket: name,
      key,
      content_type: chosen.type,
    })
    const uploadKey = key
    setUploadId(created.upload_id)
    try {
      const parts = []
      const total = Math.max(1, Math.ceil(chosen.size / PART_SIZE))
      for (let index = 0; index < total; index += 1) {
        setUploadStatus(`Uploading part ${index + 1} of ${total}…`)
        const start = index * PART_SIZE
        const data = chosen.slice(start, Math.min(start + PART_SIZE, chosen.size))
        const answer = await api.uploadObjectPart({
          account,
          region,
          bucket: name,
          key: uploadKey,
          upload_id: created.upload_id,
          part_number: index + 1,
          data,
        })
        parts.push({ part_number: index + 1, etag: answer.etag })
      }
      setUploadStatus('Completing the multipart upload…')
      await api.completeMultipartUpload({
        account,
        region,
        bucket: name,
        key: uploadKey,
        upload_id: created.upload_id,
        parts,
      })
    } catch (err) {
      // A part that never completed leaves nothing behind: discard the upload.
      await api
        .abortMultipartUpload({
          account,
          region,
          bucket: name,
          key: uploadKey,
          upload_id: created.upload_id,
        })
        .catch(() => {})
      throw err
    } finally {
      setUploadId('')
      setUploadStatus('')
    }
  }

  const cancelUpload = async () => {
    if (uploadId) {
      const key = newKey.trim() || file[0]?.name || ''
      await api
        .abortMultipartUpload({ account, region, bucket: name, key, upload_id: uploadId })
        .catch(() => {})
    }
    setUploadId('')
    setUploadStatus('')
    setUploading(false)
    setUploadError('')
    setFile([])
  }

  const upload = async () => {
    setSaving(true)
    setUploadError('')
    try {
      const chosen = file[0]
      if (chosen) {
        if (chosen.size > MAX_FILE) {
          throw new Error(
            `${chosen.name} is ${formatSize(chosen.size)}; this console uploads up to ${formatSize(MAX_FILE)}.`,
          )
        }
        // The operator's key is the whole key; with none typed, the file lands in the folder being browsed.
        const key = newKey.trim() || `${prefix}${chosen.name}`
        if (chosen.size > MULTIPART_ABOVE) {
          // Above the single-request ceiling the file goes up as parts.
          await uploadMultipart(chosen, key)
        } else {
          // The file's bytes are the body and its type is stored with it, so a PNG comes back as a PNG.
          await api.uploadObjectFile({
            account,
            region,
            bucket: name,
            key,
            file: chosen,
          })
        }
      } else {
        await api.putObject({ account, region, bucket: name, key: newKey, body: newBody })
      }
      setUploading(false)
      setNewKey('')
      setNewBody('')
      setFile([])
      await loadObjects()
    } catch (err) {
      setUploadError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const openObject = async (key) => {
    setObjectError('')
    setObjectMeta(null)
    setObjectMetaError('')
    setAnnotation(null)
    setAnnotationError('')
    setObjectTagEdit(null)
    setObjectTagError('')
    setAnnotationEdit(null)
    setAnnotationSaveError('')
    setRetentionEdit(null)
    setRetentionError('')
    setLegalHoldEdit(null)
    setLegalHoldError('')
    try {
      const answer = await api.readObject(account, region, name, key)
      setObjectView(answer)
    } catch (err) {
      setObjectView(null)
      setObjectError(err.message)
      return
    }
    // The reads beside the object follow it; their failure is not the object failing to open.
    try {
      setObjectMeta(await api.objectMeta(account, region, name, key))
    } catch (err) {
      setObjectMetaError(err.message)
    }
  }

  const openAnnotation = async (annotationName) => {
    setAnnotation(null)
    setAnnotationError('')
    try {
      setAnnotation(await api.objectAnnotation(account, region, name, objectView.key, annotationName))
    } catch (err) {
      setAnnotationError(err.message)
    }
  }

  const reloadObjectMeta = async () => {
    if (!objectView?.key) return
    setObjectMeta(await api.objectMeta(account, region, name, objectView.key))
  }

  const saveObjectTags = async (tags) => {
    setObjectTagSaving(true)
    setObjectTagError('')
    try {
      await api.editObjectTags({
        account,
        region,
        bucket: name,
        key: objectView.key,
        tags,
      })
      setObjectTagEdit(null)
      await reloadObjectMeta()
    } catch (err) {
      setObjectTagError(err.message)
    } finally {
      setObjectTagSaving(false)
    }
  }

  const saveAnnotation = async () => {
    if (!annotationEdit) return
    setAnnotationSaving(true)
    setAnnotationSaveError('')
    try {
      await api.writeObjectAnnotation({
        account,
        region,
        bucket: name,
        key: objectView.key,
        name: annotationEdit.name.trim(),
        body: annotationEdit.body,
      })
      setAnnotationEdit(null)
      await reloadObjectMeta()
    } catch (err) {
      setAnnotationSaveError(err.message)
    } finally {
      setAnnotationSaving(false)
    }
  }

  const removeAnnotation = async (annotationName) => {
    setAnnotationSaveError('')
    try {
      await api.removeObjectAnnotation({
        account,
        region,
        bucket: name,
        key: objectView.key,
        name: annotationName,
      })
      await reloadObjectMeta()
    } catch (err) {
      setAnnotationSaveError(err.message)
    }
  }

  const saveRetention = async () => {
    if (!retentionEdit) return
    setLockSaving(true)
    setRetentionError('')
    try {
      await api.setObjectRetention({
        account,
        region,
        bucket: name,
        key: objectView.key,
        mode: retentionEdit.mode?.value || 'GOVERNANCE',
        until: retentionEdit.until.trim(),
      })
      setRetentionEdit(null)
      await reloadObjectMeta()
    } catch (err) {
      setRetentionError(err.message)
    } finally {
      setLockSaving(false)
    }
  }

  const saveLegalHold = async () => {
    if (!legalHoldEdit) return
    setLockSaving(true)
    setLegalHoldError('')
    try {
      await api.setObjectLegalHold({
        account,
        region,
        bucket: name,
        key: objectView.key,
        status: legalHoldEdit.value === 'ON' ? 'ON' : 'OFF',
      })
      setLegalHoldEdit(null)
      await reloadObjectMeta()
    } catch (err) {
      setLegalHoldError(err.message)
    } finally {
      setLockSaving(false)
    }
  }

  // The eight documents the bucket page displays: each is its own GET, and a failure is an error rather than "nothing configured".
  const loadDocuments = useCallback(async () => {
    if (!account || !bucketRegion || headMissing) return
    try {
      const answer = await api.bucketDocuments(account, region, name)
      setDocuments(answer.documents || {})
      setEditable(answer.editable || {})
      setDocumentsError('')
    } catch (err) {
      setDocuments({})
      setDocumentsError(err.message)
    }
  }, [account, region, name, bucketRegion, headMissing])

  useEffect(() => {
    loadDocuments()
  }, [loadDocuments])

  // Versions and unfinished uploads are their own listings, read by the tab that shows them.
  const loadVersions = useCallback(async () => {
    if (!account || !bucketRegion || headMissing) return
    setVersionsLoading(true)
    try {
      const answer = await api.versions(account, region, name, prefix)
      setVersions(answer.versions || [])
      setVersionsNext(
        answer.truncated
          ? {
              key_marker: answer.next_key_marker || '',
              version_id_marker: answer.next_version_id_marker || '',
            }
          : null,
      )
      setVersionsError('')
    } catch (err) {
      setVersions([])
      setVersionsNext(null)
      setVersionsError(err.message)
    } finally {
      setVersionsLoading(false)
    }
  }, [account, region, name, prefix, bucketRegion, headMissing])

  const loadUploads = useCallback(async () => {
    if (!account || !bucketRegion || headMissing) return
    setUploadsLoading(true)
    try {
      const answer = await api.uploads(account, region, name, prefix)
      setUploads(answer.uploads || [])
      setUploadsNext(
        answer.truncated
          ? {
              key_marker: answer.next_key_marker || '',
              upload_id_marker: answer.next_upload_id_marker || '',
            }
          : null,
      )
      setUploadsError('')
    } catch (err) {
      setUploads([])
      setUploadsNext(null)
      setUploadsError(err.message)
    } finally {
      setUploadsLoading(false)
    }
  }, [account, region, name, prefix, bucketRegion, headMissing])

  // One listing is one page, so a long list is continued rather than shown short.
  const loadMoreVersions = async () => {
    if (!versionsNext) return
    setVersionsMore(true)
    try {
      const answer = await api.versions(
        account,
        region,
        name,
        prefix,
        versionsNext.key_marker,
        versionsNext.version_id_marker,
      )
      setVersions((held) => [...held, ...(answer.versions || [])])
      setVersionsNext(
        answer.truncated
          ? {
              key_marker: answer.next_key_marker || '',
              version_id_marker: answer.next_version_id_marker || '',
            }
          : null,
      )
      setVersionsError('')
    } catch (err) {
      setVersionsError(err.message)
    } finally {
      setVersionsMore(false)
    }
  }

  const loadMoreUploads = async () => {
    if (!uploadsNext) return
    setUploadsMore(true)
    try {
      const answer = await api.uploads(
        account,
        region,
        name,
        prefix,
        uploadsNext.key_marker,
        uploadsNext.upload_id_marker,
      )
      setUploads((held) => [...held, ...(answer.uploads || [])])
      setUploadsNext(
        answer.truncated
          ? {
              key_marker: answer.next_key_marker || '',
              upload_id_marker: answer.next_upload_id_marker || '',
            }
          : null,
      )
      setUploadsError('')
    } catch (err) {
      setUploadsError(err.message)
    } finally {
      setUploadsMore(false)
    }
  }

  useEffect(() => {
    if (tab === 'objects') loadUploads()
  }, [tab, loadUploads])

  useEffect(() => {
    if (tab === 'properties') loadVersions()
  }, [tab, loadVersions])

  // The ACL dialog opens on the ACL as S3 holds it, so a grant is read before it is changed.
  const aclTickets = useRef(0)
  const loadAcl = useCallback(
    async (key, version = '') => {
      const ticket = ++aclTickets.current
      if (!account || !key) return
      setAclReadLoading(true)
      try {
        const answer = await api.objectAcl(account, region, name, key, version)
        if (ticket !== aclTickets.current) return
        if (!answer.ok) throw new Error(answer.error || 'S3 did not answer with an ACL.')
        setAclRead(answer)
        setAclReadError('')
      } catch (err) {
        if (ticket !== aclTickets.current) return
        setAclRead(null)
        setAclReadError(err.message)
      } finally {
        if (ticket === aclTickets.current) setAclReadLoading(false)
      }
    },
    [account, region, name],
  )

  // An ACL is per version: the dialog offers the key's other versions, and reads the one chosen.
  useEffect(() => {
    if (!aclChange || !account) return undefined
    let live = true
    api
      .versions(account, region, name, aclChange.key)
      .then((answer) => {
        if (!live) return
        setAclVersions(
          (answer.versions || []).filter(
            (row) => row.key === aclChange.key && !row.latest && !row.delete_marker,
          ),
        )
        setAclVersionsError('')
      })
      .catch((err) => {
        if (!live) return
        setAclVersions([])
        setAclVersionsError(err.message)
      })
    return () => {
      live = false
    }
  }, [aclChange, account, region, name])

  useEffect(() => {
    if (!aclChange) {
      setAclRead(null)
      setAclReadError('')
      setAclSaved('')
      setAclVersion('')
      setAclVersions([])
      setAclVersionsError('')
      return
    }
    loadAcl(aclChange.key, aclVersion)
  }, [aclChange, aclVersion, loadAcl])

  // ListParts: what the upload already holds, for the row that was opened.
  useEffect(() => {
    if (!uploadView || !account) return undefined
    let live = true
    setPartsLoading(true)
    api
      .uploadParts(account, region, name, uploadView.key, uploadView.upload_id)
      .then((answer) => {
        if (!live) return
        setParts(answer.parts || [])
        setPartsNext(
          answer.truncated ? answer.next_part_number_marker || '' : null,
        )
        setPartsError('')
      })
      .catch((err) => {
        if (!live) return
        setParts([])
        setPartsNext(null)
        setPartsError(err.message)
      })
      .finally(() => {
        if (live) setPartsLoading(false)
      })
    return () => {
      live = false
    }
  }, [uploadView, account, region, name])

  const loadMoreParts = async () => {
    if (!partsNext || !uploadView) return
    setPartsMore(true)
    try {
      const answer = await api.uploadParts(
        account,
        region,
        name,
        uploadView.key,
        uploadView.upload_id,
        partsNext,
      )
      setParts((held) => [...held, ...(answer.parts || [])])
      setPartsNext(answer.truncated ? answer.next_part_number_marker || '' : null)
      setPartsError('')
    } catch (err) {
      setPartsError(err.message)
    } finally {
      setPartsMore(false)
    }
  }

  // An unconfigured document is edited from its own shape, so the operator starts from a well-formed element.
  const templateFor = (meta) =>
    meta.kind === 'json'
      ? '{\n  "Version": "2012-10-17",\n  "Statement": []\n}'
      : `<${meta.root} xmlns="http://s3.amazonaws.com/doc/2006-03-01/">\n</${meta.root}>`

  const openDocument = (label, title) => {
    setDocumentError('')
    setDocumentEdit({
      label,
      title,
      meta: editable[label],
      text: documents[label] || templateFor(editable[label] || { kind: 'xml', root: label }),
    })
  }

  const saveDocument = async () => {
    setSaving(true)
    setDocumentError('')
    try {
      await api.writeBucketDocument({
        account,
        region,
        bucket: name,
        document: documentEdit.label,
        body: documentEdit.text,
      })
      setDocumentEdit(null)
      await loadDocuments()
    } catch (err) {
      setDocumentError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const clearDocument = async () => {
    setSaving(true)
    setDocumentError('')
    try {
      await api.clearBucketDocument({
        account,
        region,
        bucket: name,
        document: documentEdit.label,
      })
      setDocumentEdit(null)
      await loadDocuments()
    } catch (err) {
      setDocumentError(err.message)
    } finally {
      setSaving(false)
    }
  }

  // Deep links: a new tab arrives with the view in the URL, so read it back once the account is known.
  useEffect(() => {
    if (!requestedKey || !account) return
    openObject(requestedKey)
  }, [requestedKey, account])

  // The copy destination list is read when the copy form opens, not on every view of the bucket page.
  useEffect(() => {
    if (!copying || !account) return undefined
    let live = true
    api
      .browse(account, 'all', 's3')
      .then((payload) => {
        if (live) setAllBuckets(payload.resources || [])
      })
      .catch(() => {
        if (live) setAllBuckets([])
      })
    return () => {
      live = false
    }
  }, [copying, account])

  const copyObject = async () => {
    if (!copying || !copyTo) return
    setSaving(true)
    setCopyError('')
    try {
      const answer = await api.copyObject({
        account,
        region,
        bucket: name,
        key: copying,
        destination: copyTo.value,
        destination_region: copyTo.region || region,
        destination_key: copyKey.trim() || copying,
      })
      if (!answer.ok) throw new Error(answer.error || 'Could not copy the object.')
      if (copyMode === 'move') {
        const removed = await api.exec({
          account,
          region,
          service: 's3',
          operation: 'delete-object',
          params: { Bucket: name, Key: copying },
        })
        if (!removed.ok) {
          throw new Error(removed.error || 'Copied, but the source could not be deleted.')
        }
      }
      setCopying(null)
      setSelected([])
      await loadObjects()
    } catch (err) {
      setCopyError(err.message)
    } finally {
      setSaving(false)
    }
  }

  // Storage class and per-object encryption are a copy onto the object itself; an ACL is its own call.
  const rewriteObject = async () => {
    if (!rewriting) return
    setSaving(true)
    setActionError('')
    try {
      const answer = await api.rewriteObject({
        account,
        region,
        bucket: name,
        key: rewriting.key,
        ...(rewriting.mode === 'storage-class'
          ? { storage_class: rewriting.value }
          : { encryption: rewriting.value }),
      })
      if (!answer.ok) throw new Error(answer.error || 'Could not change the object.')
      setNotice(
        rewriting.mode === 'storage-class'
          ? `${rewriting.key} is now ${rewriting.value}.`
          : `${rewriting.key} is now encrypted with ${rewriting.value}.`,
      )
      setRewriting(null)
      await loadObjects()
    } catch (err) {
      setActionError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const changeObjectAcl = async () => {
    if (!aclChange) return
    setSaving(true)
    setActionError('')
    try {
      const answer = await api.setObjectAcl({
        account,
        region,
        bucket: name,
        key: aclChange.key,
        canned_acl: aclChange.value,
        version_id: aclVersion,
      })
      if (!answer.ok) throw new Error(answer.error || 'Could not change the ACL.')
      setNotice(
        `${aclChange.key}${aclVersion ? ' (that version)' : ''} is now ${aclChange.value}.`,
      )
      setAclSaved(aclChange.value)
      // The dialog stays open on what S3 now holds, which is the only proof the grant landed.
      await loadAcl(aclChange.key, aclVersion)
      await loadObjects()
    } catch (err) {
      // The write's own sentence is the latest answer; an older read must not compete with it.
      setAclReadError('')
      setAclSaved('')
      setActionError(err.message)
    } finally {
      setSaving(false)
    }
  }

  // DeleteObject with a versionId: one version of one key, and the rest of the key stays.
  const removeVersion = async () => {
    if (!deletingVersion) return
    const { key, version_id: versionId } = deletingVersion
    setSaving(true)
    setVersionsError('')
    try {
      const answer = await api.deleteVersion({
        account,
        region,
        bucket: name,
        key,
        version_id: versionId,
      })
      if (!answer.ok) throw new Error(answer.error || 'Could not delete this version.')
      setDeletingVersion(null)
      setNotice(`Deleted version ${versionId} of ${key}.`)
      await loadVersions()
    } catch (err) {
      setDeletingVersion(null)
      setVersionsError(err.message)
    } finally {
      setSaving(false)
    }
  }

  // AbortMultipartUpload: the parts S3 holds for this upload are discarded with it.
  const abortUpload = async () => {
    if (!uploadView) return
    setSaving(true)
    setPartsError('')
    try {
      const answer = await api.abortMultipartUpload({
        account,
        region,
        bucket: name,
        key: uploadView.key,
        upload_id: uploadView.upload_id,
      })
      if (!answer.ok) throw new Error(answer.error || 'Could not abort this upload.')
      setNotice(`Aborted the upload of ${uploadView.key}.`)
      setUploadView(null)
      await loadUploads()
    } catch (err) {
      setPartsError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const removeObject = async () => {
    if (!deletingObject) return
    setSaving(true)
    try {
      const answer = await api.exec({
        account,
        region,
        service: 's3',
        operation: 'delete-object',
        params: { Bucket: name, Key: deletingObject },
      })
      if (!answer.ok) throw new Error(answer.error || 'Could not delete the object.')
      setDeletingObject(null)
      await loadObjects()
    } catch (err) {
      setError(err.message)
      setDeletingObject(null)
    } finally {
      setSaving(false)
    }
  }

  const save = async (change) => {
    setSaving(true)
    try {
      await api.editBucketSettings({ account, region, bucket: name, ...change })
      const answer = await api.bucketSettings(account, region, name)
      setSettings(answer.settings || null)
      setVersioningEdit(null)
      setAccessEdit(null)
      setEncryptionEdit(null)
      setTagEdit(null)
      setOwnershipEdit(null)
    } catch (err) {
      setSettingsError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const isFolder = (key) => key.endsWith('/')

  // The Type column names the format as S3's own listing does; `Object` is the fallback, not the label.
  const TYPE_LABELS = {
    csv: 'CSV',
    json: 'JSON',
    xml: 'XML',
    yaml: 'YAML',
    yml: 'YAML',
    md: 'Markdown',
    html: 'HTML',
    htm: 'HTML',
    txt: 'Text',
    log: 'Log',
    pdf: 'PDF',
    zip: 'ZIP',
    gz: 'GZIP',
    tar: 'TAR',
    parquet: 'Parquet',
    js: 'JavaScript',
    css: 'CSS',
    png: 'PNG',
    jpg: 'JPEG',
    jpeg: 'JPEG',
    gif: 'GIF',
    svg: 'SVG',
    webp: 'WebP',
    avif: 'AVIF',
    ico: 'Icon',
  }

  const extension = (key) => {
    const name = key.slice(key.lastIndexOf('/') + 1)
    const dot = name.lastIndexOf('.')
    return dot > 0 ? name.slice(dot + 1).toLowerCase() : ''
  }

  const typeLabel = (key) =>
    isFolder(key) ? 'Folder' : TYPE_LABELS[extension(key)] || 'Object'

  // Selection drives the toolbar: one for the URI/URL/Open, files only for Download, any for Delete.
  const pickedFiles = selected.filter((item) => !isFolder(item.key))
  const pickedFolders = selected.filter((item) => isFolder(item.key))
  const single = selected.length === 1 ? selected[0] : null

  const copyText = async (text, label) => {
    try {
      await navigator.clipboard.writeText(text)
      setNotice(`${label} copied`)
    } catch (err) {
      setNotice(`Could not copy: ${err.message}`)
    }
  }

  const downloadSelected = () => {
    for (const file of pickedFiles) {
      window.open(api.objectDownloadUrl(account, region, name, file.key), '_blank', 'noopener')
    }
  }

  const deleteSelected = async () => {
    setActing(true)
    setError('')
    try {
      for (const item of selected) {
        const answer = await api.exec({
          account,
          region,
          service: 's3',
          operation: 'delete-object',
          params: { Bucket: name, Key: item.key },
        })
        if (!answer.ok) throw new Error(answer.error || `Could not delete ${item.key}.`)
      }
      setSelected([])
      await loadObjects()
    } catch (err) {
      setError(err.message)
    } finally {
      setActing(false)
    }
  }

  const createFolder = async () => {
    const folder = folderName.trim().replace(/^\/+|\/+$/g, '')
    if (!folder) return
    setActing(true)
    setError('')
    try {
      const answer = await api.putObject({
        account,
        region,
        bucket: name,
        key: `${prefix}${folder}/`,
        body: '',
      })
      if (!answer.ok) throw new Error(answer.error || 'Could not create the folder.')
      setFolderOpen(false)
      setFolderName('')
      await loadObjects()
    } catch (err) {
      setError(err.message)
    } finally {
      setActing(false)
    }
  }

  // The bucket at a folder, or at its root when no prefix is named; the address bar is what the breadcrumb walks.
  const bucketLink = (atPrefix = '') => {
    const params = new URLSearchParams()
    if (region) params.set('region', region)
    if (atPrefix) params.set('prefix', atPrefix)
    return `/s3/buckets/${encodeURIComponent(name)}?${params}`
  }

  // A folder opens here; a file opens its own view in a new tab, and here when a tab is refused.
  const viewLink = (key) => {
    if (key.endsWith('/')) return bucketLink(key)
    const params = new URLSearchParams()
    if (region) params.set('region', region)
    if (prefix) params.set('prefix', prefix)
    params.set('key', key)
    return `/s3/buckets/${encodeURIComponent(name)}?${params}`
  }

  const openKey = (key) => {
    if (key.endsWith('/')) {
      navigate(viewLink(key))
      return
    }
    // `noopener` makes the returned handle null, so it cannot be used to detect a blocked tab.
    const tab = window.open(`${window.location.origin}${viewLink(key)}`, '_blank')
    if (tab) {
      tab.opener = null
      return
    }
    navigate(viewLink(key))
  }

  // The object view is a page of its own, like S3's: the list is replaced, not covered.
  const closeObject = () => {
    setObjectView(null)
    setObjectError('')
    setObjectMeta(null)
    setObjectMetaError('')
    setAnnotation(null)
    setAnnotationError('')
    const next = new URLSearchParams(searchParams)
    next.delete('key')
    setSearchParams(next, { replace: true })
  }

  const objectOpen = Boolean(objectView) || Boolean(objectError)

  const objectActions = objectView ? (
    <SpaceBetween direction="horizontal" size="xs">
      {objectView.binary && (
        <Button href={api.objectDownloadUrl(account, region, name, objectView.key)}>
          Download
        </Button>
      )}
      <Button
        onClick={() => {
          // One confirmation, then the list is the truth again.
          setDeletingObject(objectView.key)
          closeObject()
        }}
      >
        Delete
      </Button>
      <Button
        onClick={() => {
          setCopying(objectView.key)
          setCopyKey(objectView.key)
          setCopyError('')
          setCopyTo({ label: `${name} · ${region}`, value: name, region })
          closeObject()
        }}
      >
        Copy
      </Button>
      <Button variant="primary" onClick={closeObject}>
        Back to objects
      </Button>
    </SpaceBetween>
  ) : (
    <Button onClick={closeObject}>Back to objects</Button>
  )

  const startCopyMove = (mode) => {
    if (!single) return
    setCopyMode(mode)
    setCopyTo(null)
    setCopyKey(single.key)
    setCopyError('')
    setCopying(single.key)
  }

  const startRewrite = (mode) => {
    if (!single) return
    setActionError('')
    setRewriting({
      mode,
      key: single.key,
      value: mode === 'storage-class' ? single.storage || 'STANDARD' : 'AES256',
    })
  }

  const startAcl = () => {
    if (!single) return
    setActionError('')
    setAclChange({ key: single.key, value: 'private' })
  }

  // The filter narrows the folder you are in; it never moves you to another one.
  const rows = filter.trim()
    ? objects.filter((item) =>
        item.key.toLowerCase().includes(filter.trim().toLowerCase()),
      )
    : objects
  const counter = selected.length
    ? `(${selected.length}/${rows.length})`
    : rows.length === objects.length
      ? `(${rows.length})`
      : `(${rows.length} of ${objects.length})`

  // The ACL dialog's version menu: the key's current version, then the older ones S3 lists.
  const aclVersionOptions = [
    { label: 'Current version', value: '' },
    ...aclVersions.map((row) => ({
      label: `${row.version_id} · ${row.modified}`,
      value: row.version_id,
    })),
  ]
  const aclVersionOption =
    aclVersionOptions.find((option) => option.value === aclVersion) || aclVersionOptions[0]

  const objectsTab = (
    <Container
      header={
        <Header
          variant="h2"
          counter={counter}
          description="Objects are the fundamental entities stored in Amazon S3."
          actions={
            <SpaceBetween direction="horizontal" size="xs">
              <Button iconName="refresh" ariaLabel="Refresh" onClick={loadObjects} />
              <Button
                disabled={!single}
                onClick={() => copyText(`s3://${name}/${single.key}`, 'S3 URI')}
              >
                Copy S3 URI
              </Button>
              <Button
                disabled={!single}
                onClick={() =>
                  copyText(
                    window.location.origin +
                      api.objectDownloadUrl(account, region, name, single.key),
                    'Object URL',
                  )
                }
              >
                Copy URL
              </Button>
              <Button
                disabled={!pickedFiles.length || Boolean(pickedFolders.length)}
                onClick={downloadSelected}
              >
                Download
              </Button>
              <Button disabled={!single} onClick={() => openKey(single.key)}>
                Open
              </Button>
              <Button disabled={!selected.length} loading={acting} onClick={deleteSelected}>
                Delete
              </Button>
              <ButtonDropdown
                disabled={!single}
                items={[
                  { id: 'copy', text: 'Copy' },
                  { id: 'move', text: 'Move' },
                  { id: 'storage-class', text: 'Edit storage class' },
                  { id: 'sse', text: 'Edit server-side encryption' },
                  { id: 'acl', text: 'Make public using ACL' },
                ]}
                onItemClick={({ detail }) => {
                  if (detail.id === 'copy' || detail.id === 'move') {
                    startCopyMove(detail.id)
                    return
                  }
                  if (detail.id === 'acl') {
                    startAcl()
                    return
                  }
                  startRewrite(detail.id)
                }}
              >
                Actions
              </ButtonDropdown>
              <Button onClick={() => setFolderOpen(true)}>Create folder</Button>
              <Button variant="primary" onClick={() => setUploading(true)}>
                Upload
              </Button>
            </SpaceBetween>
          }
        >
          Objects
        </Header>
      }
    >
      <SpaceBetween size="m">
        {error && (
          <Alert type="error" header="Could not read this bucket">
            {error}
          </Alert>
        )}
        {notice && (
          <Alert type="success" dismissible onDismiss={() => setNotice('')}>
            {notice}
          </Alert>
        )}
        <div style={{ maxWidth: 420 }}>
          <Input
            value={filter}
            onChange={({ detail }) => setFilter(detail.value)}
            placeholder="Filter by name"
            ariaLabel="Filter objects by name"
            type="search"
          />
        </div>
        <Table
          items={rows}
          loading={loading}
          loadingText="Reading objects"
          trackBy="key"
          selectionType="multi"
          selectedItems={selected}
          onSelectionChange={({ detail }) => setSelected(detail.selectedItems)}
          columnDefinitions={[
            {
              id: 'key',
              header: 'Name',
              cell: (item) => <Link to={viewLink(item.key)}>{item.key}</Link>,
              sortingField: 'key',
            },
            { id: 'type', header: 'Type', cell: (item) => typeLabel(item.key), width: 110 },
            {
              id: 'modified',
              header: 'Last modified',
              cell: (item) => item.modified,
              width: 230,
            },
            { id: 'size', header: 'Size', cell: (item) => item.size, width: 110 },
            {
              id: 'storage',
              header: 'Storage class',
              cell: (item) => item.storage || 'STANDARD',
              width: 160,
            },
          ]}
          empty={
            <Box textAlign="center">
              <SpaceBetween size="xs">
                <Box fontSize="heading-s">No objects</Box>
                <Box color="text-body-secondary">
                  {filter.trim()
                    ? `Nothing in this folder matches ${filter.trim()}.`
                    : "You don't have any objects in this folder."}
                </Box>
              </SpaceBetween>
            </Box>
          }
        />
        {nextToken && (
          <Box textAlign="center">
            <Button loading={moreLoading} onClick={loadMore}>
              Load more objects
            </Button>
          </Box>
        )}
        <Container
          header={
            <Header
              variant="h2"
              counter={`(${uploads.length})`}
              description="Uploads that were started in this folder and never completed. They hold parts S3 keeps until they are aborted."
              actions={
                <Button
                  iconName="refresh"
                  ariaLabel="Refresh incomplete uploads"
                  onClick={loadUploads}
                />
              }
            >
              Incomplete multipart uploads
            </Header>
          }
        >
          <SpaceBetween size="m">
            {uploadsError && (
              <Alert type="error" header="Could not list this bucket's incomplete uploads">
                {uploadsError}
              </Alert>
            )}
            {!uploadsError && !uploadsLoading && uploads.length === 0 ? (
              <Box color="text-body-secondary">No incomplete uploads in this folder.</Box>
            ) : uploadsError ? null : (
              <Table
                items={uploads}
                loading={uploadsLoading}
                loadingText="Reading incomplete uploads"
                trackBy="upload_id"
                columnDefinitions={[
                  { id: 'key', header: 'Name', cell: (item) => item.key },
                  {
                    id: 'upload_id',
                    header: 'Upload ID',
                    cell: (item) => <span className="mono">{item.upload_id}</span>,
                  },
                  {
                    id: 'initiated',
                    header: 'Initiated',
                    cell: (item) => item.initiated,
                    width: 230,
                  },
                  {
                    id: 'storage',
                    header: 'Storage class',
                    cell: (item) => item.storage || 'STANDARD',
                    width: 160,
                  },
                  {
                    id: 'actions',
                    header: '',
                    width: 110,
                    cell: (item) => (
                      <Button
                        variant="inline-link"
                        ariaLabel={`Show the parts of the upload of ${item.key}`}
                        onClick={() => setUploadView(item)}
                      >
                        Parts
                      </Button>
                    ),
                  },
                ]}
              />
            )}
            {uploadsNext && (
              <Box textAlign="center">
                <Button loading={uploadsMore} onClick={loadMoreUploads}>
                  Load more uploads
                </Button>
              </Box>
            )}
          </SpaceBetween>
        </Container>
      </SpaceBetween>
    </Container>
  )

  // The two child listings the bucket page shows for this bucket alone: S3 Files and the access points attached to it.
  useEffect(() => {
    if (!account || !bucketRegion || headMissing) return undefined
    let live = true
    api
      .s3FileSystems(account, region)
      .then((answer) => {
        if (!live) return
        setFiles((answer.items || []).filter((row) => row.bucket === name))
        setFilesError('')
      })
      .catch((err) => {
        if (live) setFilesError(err.message)
      })
    api
      .accessPoints(account, region, 'general')
      .then((answer) => {
        if (!live) return
        // The listing is account-wide; this tab is about one bucket's points.
        setPoints((answer.access_points || []).filter((row) => row.bucket === name))
        setPointsError('')
      })
      .catch((err) => {
        if (live) setPointsError(err.message)
      })
    return () => {
      live = false
    }
  }, [account, region, name, bucketRegion, headMissing])

  // One card per subresource, the way the console lays them out: the document as S3 answers it, with the control that writes it.
  const documentCard = (label, title, description) => {
    const meta = editable[label] || {}
    const aclLocked = label === 'acl' && settings?.ownership === 'BucketOwnerEnforced'
    return (
      <Container
        key={label}
        header={
          <Header
            variant="h2"
            description={description}
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                <Button
                  ariaLabel={`Edit ${label}`}
                  disabled={aclLocked}
                  onClick={() => openDocument(label, title)}
                >
                  Edit
                </Button>
                {documents[label] && meta.delete && (
                  <Button
                    ariaLabel={`Delete ${label}`}
                    loading={saving}
                    onClick={() => {
                      setDocumentError('')
                      setDocumentEdit({
                        label,
                        title,
                        meta,
                        text: documents[label],
                        deleting: true,
                      })
                    }}
                  >
                    Delete
                  </Button>
                )}
              </SpaceBetween>
            }
          >
            {title}
          </Header>
        }
      >
        {aclLocked && (
          <Box color="text-body-secondary" fontSize="body-s">
            ACLs are disabled for this bucket (Object Ownership: bucket owner enforced),
            so S3 refuses to change this policy. Object Ownership, above, turns them on.
          </Box>
        )}
        {documents[label] ? (
          <pre className="result-body">{documents[label]}</pre>
        ) : (
          <Box color="text-body-secondary">Not configured.</Box>
        )}
      </Container>
    )
  }

  // A failed read is not the same as an empty document, so every tab says the read failed rather than looking unconfigured.
  const documentsAlert = (
    <Alert type="error" header="Could not read this bucket's configuration">
      {documentsError}
    </Alert>
  )

  // S3 answers three ways, so the card does too: never on, on, and suspended after being on.
  const versioningState =
    settings?.versioning_status || (settings?.versioning ? 'Enabled' : 'Disabled')
  const versioningTone =
    versioningState === 'Enabled'
      ? 'success'
      : versioningState === 'Suspended'
        ? 'warning'
        : 'stopped'

  const propertiesTab = (
    <SpaceBetween size="l">
      {settingsError && (
        <Alert type="error" header="Could not read this bucket's properties">
          {settingsError}
        </Alert>
      )}
      {documentsError && documentsAlert}
      <Container header={<Header variant="h2">Bucket overview</Header>}>
        <SpaceBetween size="xs">
          <Box>
            <Box variant="awsui-key-label">AWS Region</Box>
            {regionName(region)} <span className="mono">{region}</span>
          </Box>
          <Box>
            <Box variant="awsui-key-label">Amazon Resource Name (ARN)</Box>
            <span className="mono">{`arn:aws:s3:::${name}`}</span>
          </Box>
          <Box>
            <Box variant="awsui-key-label">Creation date</Box>
            {settings?.created || dash}
          </Box>
        </SpaceBetween>
      </Container>

      <Container header={<Header variant="h2">Bucket Versioning</Header>}>
        <SpaceBetween size="m">
          <Box>
            <Box variant="awsui-key-label">Bucket Versioning</Box>
            <StatusIndicator type={versioningTone}>{versioningState}</StatusIndicator>
          </Box>
          {versioningEdit === null ? (
            <Box>
              <Button
                ariaLabel="Edit bucket versioning"
                disabled={!settings}
                onClick={() =>
                  setVersioningEdit(versioningState === 'Enabled' ? 'Enabled' : 'Suspended')
                }
              >
                Edit
              </Button>
            </Box>
          ) : (
            <SpaceBetween size="s">
              <RadioGroup
                value={versioningEdit}
                onChange={({ detail }) => setVersioningEdit(detail.value)}
                items={[
                  { value: 'Enabled', label: 'Enable' },
                  { value: 'Suspended', label: 'Suspend' },
                ]}
              />
              <Box color="text-body-secondary" fontSize="body-s">
                S3 never turns versioning back off: an enabled bucket can only be suspended,
                and it stays that way for the objects already versioned.
              </Box>
              <SpaceBetween direction="horizontal" size="xs">
                <Button variant="link" onClick={() => setVersioningEdit(null)}>
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  ariaLabel="Save bucket versioning"
                  loading={saving}
                  onClick={() => save({ versioning_status: versioningEdit })}
                >
                  Save
                </Button>
              </SpaceBetween>
            </SpaceBetween>
          )}
        </SpaceBetween>
      </Container>

      <Container header={<Header variant="h2">Default encryption</Header>}>
        {encryptionEdit === null ? (
          <SpaceBetween size="s">
            <Box>
              <Box variant="awsui-key-label">Encryption type</Box>
              {settings?.encryption || 'AES256'}
              {settings?.bucket_key ? ' · bucket key enabled' : ''}
            </Box>
            <Box>
              <Button
                ariaLabel="Edit default encryption"
                onClick={() => {
                  setEncryptionEdit(settings?.encryption || 'AES256')
                  setBucketKeyEdit(Boolean(settings?.bucket_key))
                }}
              >
                Edit
              </Button>
            </Box>
          </SpaceBetween>
        ) : (
          <SpaceBetween size="m">
            <RadioGroup
              value={encryptionEdit}
              onChange={({ detail }) => setEncryptionEdit(detail.value)}
              items={ENCRYPTION.map(([value, label]) => ({ value, label }))}
            />
            <Checkbox
              checked={bucketKeyEdit}
              disabled={!encryptionEdit.startsWith('aws:kms')}
              onChange={({ detail }) => setBucketKeyEdit(detail.checked)}
            >
              Bucket Key
            </Checkbox>
            <SpaceBetween direction="horizontal" size="xs">
              <Button
                variant="primary"
                ariaLabel="Save default encryption"
                loading={saving}
                onClick={() =>
                  save({ encryption: encryptionEdit, bucket_key: bucketKeyEdit })
                }
              >
                Save
              </Button>
              <Button variant="link" onClick={() => setEncryptionEdit(null)}>
                Cancel
              </Button>
              <Button
                variant="link"
                loading={saving}
                onClick={() => save({ remove_encryption: true })}
              >
                Remove default encryption
              </Button>
            </SpaceBetween>
          </SpaceBetween>
        )}
      </Container>

      <Container
        header={
          <Header
            variant="h2"
            counter={`(${settings?.tags?.length || 0})`}
            actions={
              <SpaceBetween direction="horizontal" size="xs">
                <Button
                  ariaLabel="Edit bucket tags"
                  onClick={() =>
                    setTagEdit(
                      (settings?.tags || []).length
                        ? (settings.tags || []).map((tag) => ({ ...tag }))
                        : [{ Key: '', Value: '' }],
                    )
                  }
                >
                  {(settings?.tags || []).length ? 'Edit' : 'Add tags'}
                </Button>
                {(settings?.tags || []).length > 0 && (
                  <Button
                    ariaLabel="Remove bucket tags"
                    loading={saving}
                    onClick={() => save({ remove_tags: true })}
                  >
                    Remove tags
                  </Button>
                )}
              </SpaceBetween>
            }
          >
            Tags
          </Header>
        }
      >
        {tagEdit !== null ? (
          <SpaceBetween size="m">
            {tagEdit.map((tag, index) => (
              <SpaceBetween key={index} direction="horizontal" size="xs">
                <Input
                  value={tag.Key}
                  onChange={({ detail }) =>
                    setTagEdit((rows) =>
                      rows.map((item, at) =>
                        at === index ? { ...item, Key: detail.value } : item,
                      ),
                    )
                  }
                  placeholder="Key"
                  ariaLabel={`Tag key ${index + 1}`}
                />
                <Input
                  value={tag.Value}
                  onChange={({ detail }) =>
                    setTagEdit((rows) =>
                      rows.map((item, at) =>
                        at === index ? { ...item, Value: detail.value } : item,
                      ),
                    )
                  }
                  placeholder="Value"
                  ariaLabel={`Tag value ${index + 1}`}
                />
                <Button
                  ariaLabel={`Remove tag ${index + 1}`}
                  disabled={tagEdit.length === 1}
                  onClick={() =>
                    setTagEdit((rows) => rows.filter((_item, at) => at !== index))
                  }
                >
                  Remove
                </Button>
              </SpaceBetween>
            ))}
            <SpaceBetween direction="horizontal" size="xs">
              <Button
                ariaLabel="Add another tag"
                onClick={() =>
                  setTagEdit((rows) => [...rows, { Key: '', Value: '' }])
                }
              >
                Add tag
              </Button>
              <Button
                variant="primary"
                ariaLabel="Save bucket tags"
                loading={saving}
                disabled={tagEdit.some((tag) => !tag.Key.trim())}
                onClick={() => save({ tags: tagEdit })}
              >
                Save
              </Button>
              <Button variant="link" onClick={() => setTagEdit(null)}>
                Cancel
              </Button>
            </SpaceBetween>
          </SpaceBetween>
        ) : (settings?.tags || []).length === 0 ? (
          <Box color="text-body-secondary">No tags associated with this bucket.</Box>
        ) : (
          <Table
            items={settings.tags}
            trackBy="Key"
            columnDefinitions={[
              { id: 'key', header: 'Key', cell: (item) => item.Key },
              { id: 'value', header: 'Value', cell: (item) => item.Value },
            ]}
          />
        )}
      </Container>
      {documentCard(
        'logging',
        'Server access logging',
        "Log requests for access to your bucket.",
      )}
      {documentCard(
        'notifications',
        'Event notifications',
        'Send a notification when specific events occur in your bucket.',
      )}
      {documentCard(
        'website',
        'Static website hosting',
        'Serve an index document and an error document from this bucket.',
      )}
      <Container
        header={
          <Header
            variant="h2"
            counter={`(${versions.length})`}
            description="Every version of every object under this folder, as ListObjectVersions reports it."
            actions={
              <Button iconName="refresh" ariaLabel="Refresh versions" onClick={loadVersions} />
            }
          >
            Versions
          </Header>
        }
      >
        <SpaceBetween size="m">
          {versionsError && (
            <Alert type="error" header="Could not list this bucket's versions">
              {versionsError}
            </Alert>
          )}
          {!versionsError && !versionsLoading && versions.length === 0 ? (
            <Box color="text-body-secondary">
              {settings?.versioning_status === 'Enabled' ||
              settings?.versioning_status === 'Suspended'
                ? 'No versions in this folder yet.'
                : 'Versioning has never been enabled on this bucket, so every object has a single version.'}
            </Box>
          ) : versionsError ? null : (
            <Table
              items={versions}
              loading={versionsLoading}
              loadingText="Reading versions"
              trackBy="version_id"
              columnDefinitions={[
                {
                  id: 'key',
                  header: 'Name',
                  // Only the current version is what the object view opens; an older one is named, not linked.
                  cell: (item) =>
                    item.latest && !item.delete_marker ? (
                      <Link to={viewLink(item.key)}>{item.key}</Link>
                    ) : (
                      <span className="mono">{item.key}</span>
                    ),
                },
                { id: 'version_id', header: 'Version ID', cell: (item) => item.version_id },
                {
                  id: 'kind',
                  header: 'Type',
                  cell: (item) => (item.delete_marker ? 'Delete marker' : 'Version'),
                  width: 130,
                },
                {
                  id: 'latest',
                  header: 'Latest',
                  cell: (item) => (item.latest ? 'Yes' : dash),
                  width: 90,
                },
                {
                  id: 'size',
                  header: 'Size',
                  cell: (item) =>
                    item.delete_marker || item.size === ''
                      ? dash
                      : formatSize(Number(item.size)),
                  width: 110,
                },
                {
                  id: 'modified',
                  header: 'Last modified',
                  cell: (item) => item.modified,
                  width: 230,
                },
                {
                  id: 'storage',
                  header: 'Storage class',
                  cell: (item) => item.storage || dash,
                  width: 160,
                },
                {
                  id: 'actions',
                  header: '',
                  width: 190,
                  cell: (item) => (
                    <SpaceBetween direction="horizontal" size="xs">
                      {!item.delete_marker && (
                        <Button
                          variant="inline-link"
                          ariaLabel={`Download version ${item.version_id} of ${item.key}`}
                          href={api.objectDownloadUrl(
                            account,
                            region,
                            name,
                            item.key,
                            item.version_id,
                          )}
                        >
                          Download
                        </Button>
                      )}
                      <Button
                        variant="inline-link"
                        ariaLabel={`Delete version ${item.version_id} of ${item.key}`}
                        onClick={() => setDeletingVersion(item)}
                      >
                        Delete
                      </Button>
                    </SpaceBetween>
                  ),
                },
              ]}
            />
          )}
          {versionsNext && (
            <Box textAlign="center">
              <Button loading={versionsMore} onClick={loadMoreVersions}>
                Load more versions
              </Button>
            </Box>
          )}
        </SpaceBetween>
      </Container>
    </SpaceBetween>
  )

  const permissionsTab = (
    <SpaceBetween size="l">
      <Container
        header={
          <Header
            variant="h2"
            description="Public access is granted to buckets and objects through access control lists (ACLs), bucket policies, access point policies, or all."
          >
            Block public access (bucket settings)
          </Header>
        }
      >
        <SpaceBetween size="xs">
          <Box>
            <Box variant="awsui-key-label">Block all public access</Box>
            <StatusIndicator
              type={
                Object.values(settings?.block_public_access || {}).every(Boolean)
                  ? 'success'
                  : 'warning'
              }
            >
              {Object.values(settings?.block_public_access || {}).every(Boolean)
                ? 'On'
                : 'Off'}
            </StatusIndicator>
          </Box>
          <SpaceBetween size="s">
            {Object.entries(accessEdit ?? settings?.block_public_access ?? {}).map(
              ([setting, value]) => (
                <Toggle
                  key={setting}
                  checked={Boolean(value)}
                  onChange={({ detail }) =>
                    setAccessEdit({
                      ...(accessEdit ?? settings?.block_public_access ?? {}),
                      [setting]: detail.checked,
                    })
                  }
                >
                  {setting}
                </Toggle>
              ),
            )}
            <SpaceBetween direction="horizontal" size="xs">
              <Button
                variant="primary"
                loading={saving}
                disabled={accessEdit === null}
                onClick={() => save({ block_public_access: accessEdit })}
              >
                Save
              </Button>
              {settings?.public_access_block_configured && (
                <Button
                  variant="link"
                  loading={saving}
                  onClick={() => save({ remove_public_access_block: true })}
                >
                  Remove block public access configuration
                </Button>
              )}
            </SpaceBetween>
            {settings && !settings.public_access_block_configured && (
              <Box color="text-body-secondary">
                No block public access configuration is set on this bucket.
              </Box>
            )}
          </SpaceBetween>
        </SpaceBetween>
      </Container>

      <Container
        header={
          <Header
            variant="h2"
            description="Object Ownership decides whether ACLs work on this bucket. Bucket owner enforced turns ACLs off; bucket owner preferred leaves them available to the grant dialog."
            actions={
              ownershipEdit === null ? (
                <Button
                  ariaLabel="Edit object ownership"
                  disabled={!settings}
                  onClick={() =>
                    setOwnershipEdit(settings?.ownership || 'BucketOwnerEnforced')
                  }
                >
                  Edit
                </Button>
              ) : null
            }
          >
            Object Ownership
          </Header>
        }
      >
        {ownershipEdit === null ? (
          <SpaceBetween size="xs">
            <StatusIndicator
              type={
                settings?.ownership === 'BucketOwnerPreferred' ? 'success' : 'stopped'
              }
            >
              {settings?.ownership === 'BucketOwnerPreferred'
                ? 'ACLs enabled - bucket owner preferred'
                : 'ACLs disabled - bucket owner enforced'}
            </StatusIndicator>
            <Box color="text-body-secondary" fontSize="body-s">
              The object ACL dialog writes grants only where ACLs are enabled.
            </Box>
          </SpaceBetween>
        ) : (
          <SpaceBetween size="m">
            <RadioGroup
              value={ownershipEdit}
              onChange={({ detail }) => setOwnershipEdit(detail.value)}
              items={[
                {
                  value: 'BucketOwnerEnforced',
                  label: 'ACLs disabled (bucket owner enforced)',
                },
                {
                  value: 'BucketOwnerPreferred',
                  label: 'ACLs enabled (bucket owner preferred)',
                },
              ]}
            />
            <Box color="text-body-secondary" fontSize="body-s">
              The objects and their bytes stay where they are. Turning ACLs off stops
existing grants from applying, and turning them back on does not restore them.
            </Box>
            <SpaceBetween direction="horizontal" size="xs">
              <Button variant="link" onClick={() => setOwnershipEdit(null)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                ariaLabel="Save object ownership"
                loading={saving}
                onClick={() => save({ ownership: ownershipEdit })}
              >
                Save
              </Button>
            </SpaceBetween>
          </SpaceBetween>
        )}
      </Container>

      {documentsError && documentsAlert}
      {documentCard(
        'policy',
        'Bucket policy',
        'The bucket policy, written in JSON, provides access to the objects stored in the bucket.',
      )}
      {documentCard(
        'acl',
        'Access control list (ACL)',
        'Grant basic read/write permissions to other AWS accounts.',
      )}
      {documentCard(
        'cors',
        'Cross-origin resource sharing (CORS)',
        'The CORS configuration defines how client web applications in one domain interact with resources in another.',
      )}
    </SpaceBetween>
  )

  const managementTab = (
    <SpaceBetween size="l">
      {documentsError && documentsAlert}
      {documentCard(
        'lifecycle',
        'Lifecycle configuration',
        'A lifecycle configuration is a set of rules that define actions that S3 applies to a group of objects.',
      )}
      {documentCard(
        'replication',
        'Replication rules',
        'Replication rules define what S3 applies to objects when it copies them to another bucket.',
      )}
    </SpaceBetween>
  )

  const fileSystemsTab = (
    <Container
      header={
        <Header
          variant="h2"
          counter={`(${files.length})`}
          description="File systems give S3 data file-level access; this lists the ones mounted on this bucket."
        >
          File systems
        </Header>
      }
    >
      <SpaceBetween size="m">
        {filesError && (
          <Alert type="error" header="Could not read the file systems">
            {filesError}
          </Alert>
        )}
        <Table
          items={files}
          trackBy="fileSystemId"
          columnDefinitions={[
            {
              id: 'id',
              header: 'File system ID',
              cell: (item) => <span className="mono">{item.fileSystemId}</span>,
            },
            { id: 'name', header: 'Name', cell: (item) => item.name || dash },
            { id: 'status', header: 'Status', cell: (item) => item.status, width: 140 },
          ]}
          empty={
            filesError ? (
              <Box textAlign="center" color="text-body-secondary">
                The listing could not be read, so this is not a count of zero.
              </Box>
            ) : (
              <Box textAlign="center">
                <SpaceBetween size="xs">
                  <Box color="text-body-secondary">
                    You don&apos;t have any file systems in this bucket.
                  </Box>
                  <Button variant="link" onClick={() => navigate('/s3/files')}>
                    All file systems
                  </Button>
                </SpaceBetween>
              </Box>
            )
          }
        />
      </SpaceBetween>
    </Container>
  )

  const accessPointsTab = (
    <Container
      header={
        <Header
          variant="h2"
          counter={`(${points.length})`}
          description="Access points are named network endpoints attached to this bucket."
          actions={
            <SpaceBetween direction="horizontal" size="xs">
              <Button
                variant="primary"
                onClick={() => navigate(`/s3/access-points/create?region=${region}`)}
              >
                Create access point
              </Button>
            </SpaceBetween>
          }
        >
          Access Points for general purpose buckets
        </Header>
      }
    >
      <SpaceBetween size="m">
        {pointsError && (
          <Alert type="error" header="Could not read the access points">
            {pointsError}
          </Alert>
        )}
        <Table
          items={points}
          trackBy={(row) => row.arn || row.name}
          columnDefinitions={[
            { id: 'name', header: 'Name', cell: (row) => row.name },
            { id: 'type', header: 'Data source type', cell: () => 'Bucket', width: 150 },
            {
              id: 'alias',
              header: 'Access Point alias',
              cell: (row) => <span className="mono">{row.alias || dash}</span>,
            },
            { id: 'origin', header: 'Network origin', cell: (row) => row.network_origin, width: 150 },
          ]}
          empty={
            pointsError ? (
              <Box textAlign="center" color="text-body-secondary">
                The listing could not be read, so this is not a count of zero.
              </Box>
            ) : (
              <Box textAlign="center">
                <SpaceBetween size="xs">
                  <Box color="text-body-secondary">
                    You don&apos;t have any access points on this bucket.
                  </Box>
                  <Button variant="link" onClick={() => navigate('/s3/access-points')}>
                    All access points
                  </Button>
                </SpaceBetween>
              </Box>
            )
          }
        />
      </SpaceBetween>
    </Container>
  )

  // The reads that sit beside an object rather than in it: each is its own GET, so a failure names the read that failed.
  const metaFailed = (label) => {
    const reason = objectMeta?.errors?.[label]
    return reason ? (
      <Alert type="error" header={`Could not read the object's ${label.replace('_', ' ')}`}>
        {reason}
      </Alert>
    ) : null
  }

  const objectContent = objectError ? (
    <Alert type="error">{objectError}</Alert>
  ) : (
    <SpaceBetween size="m">
      {/* What only HeadObject knows: a GET's bytes carry none of it. */}
      <ColumnLayout columns={4} variant="text-grid">
        <div>
          <Box variant="awsui-key-label">Size</Box>
          {formatSize(objectView?.size)}
        </div>
        <div>
          <Box variant="awsui-key-label">Type</Box>
          <span className="mono">{objectView?.content_type}</span>
        </div>
        <div>
          <Box variant="awsui-key-label">ETag</Box>
          <span className="mono">{objectView?.etag || dash}</span>
        </div>
        <div>
          <Box variant="awsui-key-label">Last modified</Box>
          {objectView?.last_modified || dash}
        </div>
      </ColumnLayout>
      {objectView?.binary ? (
        <Alert type="info" header="This object is not text">
          It is stored as <span className="mono">{objectView.content_type}</span>, so the page
          offers it as a download rather than showing bytes that would not mean anything.
        </Alert>
      ) : (
        <SpaceBetween size="xs">
          <pre className="result-body">{objectView?.body}</pre>
          {objectView?.truncated && (
            <Box color="text-body-secondary" fontSize="body-s">
              Showing the first 20 000 characters. Download to see all of it.
            </Box>
          )}
        </SpaceBetween>
      )}
    </SpaceBetween>
  )

  const objectTab = objectError ? null : (
    <Tabs
      tabs={[
        { id: 'content', label: 'Content', content: objectContent },
        {
          id: 'tags',
          label: 'Tags',
          content: objectMetaError ? (
            <Alert type="error" header="Could not read this object's tags">
              {objectMetaError}
            </Alert>
          ) : (
            <SpaceBetween size="m">
              {metaFailed('tags')}
              {objectTagError && <Alert type="error">{objectTagError}</Alert>}
              {objectTagEdit ? (
                <SpaceBetween size="s">
                  {objectTagEdit.map((tag, index) => (
                    <SpaceBetween
                      key={index}
                      direction="horizontal"
                      size="xs"
                      alignItems="end"
                    >
                      <Input
                        value={tag.Key}
                        onChange={({ detail }) =>
                          setObjectTagEdit((rows) =>
                            rows.map((item, at) =>
                              at === index ? { ...item, Key: detail.value } : item,
                            ),
                          )
                        }
                        placeholder="Key"
                        ariaLabel={`Object tag key ${index + 1}`}
                      />
                      <Input
                        value={tag.Value}
                        onChange={({ detail }) =>
                          setObjectTagEdit((rows) =>
                            rows.map((item, at) =>
                              at === index ? { ...item, Value: detail.value } : item,
                            ),
                          )
                        }
                        placeholder="Value"
                        ariaLabel={`Object tag value ${index + 1}`}
                      />
                      <Button
                        ariaLabel={`Remove object tag ${index + 1}`}
                        disabled={objectTagEdit.length === 1}
                        onClick={() =>
                          setObjectTagEdit((rows) => rows.filter((_item, at) => at !== index))
                        }
                      >
                        Remove
                      </Button>
                    </SpaceBetween>
                  ))}
                  <SpaceBetween direction="horizontal" size="xs">
                    <Button
                      ariaLabel="Add another object tag"
                      onClick={() =>
                        setObjectTagEdit((rows) => [...rows, { Key: '', Value: '' }])
                      }
                    >
                      Add tag
                    </Button>
                    <Button
                      variant="primary"
                      ariaLabel="Save object tags"
                      loading={objectTagSaving}
                      disabled={objectTagEdit.some((tag) => !tag.Key.trim())}
                      onClick={() => saveObjectTags(objectTagEdit)}
                    >
                      Save
                    </Button>
                    <Button variant="link" onClick={() => setObjectTagEdit(null)}>
                      Cancel
                    </Button>
                  </SpaceBetween>
                </SpaceBetween>
              ) : (
                <SpaceBetween size="s">
                  <SpaceBetween direction="horizontal" size="xs">
                    <Button
                      ariaLabel="Edit object tags"
                      onClick={() => {
                        setObjectTagError('')
                        const rows = (objectMeta?.tags || []).map((tag) => ({
                          Key: tag.Key,
                          Value: tag.Value,
                        }))
                        setObjectTagEdit(rows.length ? rows : [{ Key: '', Value: '' }])
                      }}
                    >
                      Edit tags
                    </Button>
                    {(objectMeta?.tags || []).length > 0 && (
                      <Button
                        ariaLabel="Remove object tags"
                        loading={objectTagSaving}
                        onClick={() => saveObjectTags([])}
                      >
                        Remove tags
                      </Button>
                    )}
                  </SpaceBetween>
                  {(objectMeta?.tags || []).length === 0 && !objectMeta?.errors?.tags ? (
                    <Box color="text-body-secondary">This object has no tags.</Box>
                  ) : (
                    <Table
                      items={objectMeta?.tags || []}
                      trackBy="Key"
                      columnDefinitions={[
                        { id: 'key', header: 'Key', cell: (tag) => tag.Key },
                        { id: 'value', header: 'Value', cell: (tag) => tag.Value },
                      ]}
                    />
                  )}
                </SpaceBetween>
              )}
            </SpaceBetween>
          ),
        },
        {
          id: 'annotations',
          label: 'Annotations',
          content: objectMetaError ? (
            <Alert type="error" header="Could not read this object's annotations">
              {objectMetaError}
            </Alert>
          ) : (
            <SpaceBetween size="m">
              {metaFailed('annotations')}
              {annotationError && <Alert type="error">{annotationError}</Alert>}
              {annotationSaveError && <Alert type="error">{annotationSaveError}</Alert>}
              {annotationEdit ? (
                <SpaceBetween size="s">
                  <Input
                    value={annotationEdit.name}
                    onChange={({ detail }) =>
                      setAnnotationEdit((held) => ({ ...held, name: detail.value }))
                    }
                    placeholder="Annotation name"
                    ariaLabel="Annotation name"
                  />
                  <Textarea
                    value={annotationEdit.body}
                    onChange={({ detail }) =>
                      setAnnotationEdit((held) => ({ ...held, body: detail.value }))
                    }
                    rows={6}
                    placeholder="Annotation content"
                    ariaLabel="Annotation content"
                  />
                  <SpaceBetween direction="horizontal" size="xs">
                    <Button
                      variant="primary"
                      loading={annotationSaving}
                      disabled={!annotationEdit.name.trim()}
                      onClick={saveAnnotation}
                    >
                      Save annotation
                    </Button>
                    <Button variant="link" onClick={() => setAnnotationEdit(null)}>
                      Cancel
                    </Button>
                  </SpaceBetween>
                </SpaceBetween>
              ) : (
                <SpaceBetween size="s">
                  <Button
                    ariaLabel="Add annotation"
                    onClick={() => {
                      setAnnotationSaveError('')
                      setAnnotationEdit({ name: '', body: '' })
                    }}
                  >
                    Add annotation
                  </Button>
                  {(objectMeta?.annotations || []).length === 0 && !objectMeta?.errors?.annotations ? (
                    <Box color="text-body-secondary">This object has no annotations.</Box>
                  ) : (
                    <Table
                      items={objectMeta?.annotations || []}
                      trackBy="name"
                      columnDefinitions={[
                        {
                          id: 'name',
                          header: 'Name',
                          cell: (row) => (
                            <Button variant="inline-link" onClick={() => openAnnotation(row.name)}>
                              {row.name}
                            </Button>
                          ),
                        },
                        {
                          id: 'size',
                          header: 'Size',
                          width: 110,
                          cell: (row) => formatSize(Number(row.size)),
                        },
                        { id: 'modified', header: 'Last modified', cell: (row) => row.modified },
                        {
                          id: 'actions',
                          header: '',
                          width: 120,
                          cell: (row) => (
                            <Button
                              variant="inline-link"
                              ariaLabel={`Remove annotation ${row.name}`}
                              onClick={() => removeAnnotation(row.name)}
                            >
                              Remove
                            </Button>
                          ),
                        },
                      ]}
                    />
                  )}
                </SpaceBetween>
              )}
              {annotation && (
                <div>
                  <Box variant="awsui-key-label">{annotation.name}</Box>
                  <pre className="result-body">{annotation.body}</pre>
                </div>
              )}
            </SpaceBetween>
          ),
        },
        {
          id: 'object-lock',
          label: 'Object Lock',
          content: objectMetaError ? (
            <Alert type="error" header="Could not read this object's Object Lock state">
              {objectMetaError}
            </Alert>
          ) : (
            <SpaceBetween size="m">
              {metaFailed('retention')}
              {metaFailed('legal_hold')}
              <div>
                <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                  <Box variant="awsui-key-label">Retention</Box>
                  <Button
                    ariaLabel="Edit retention"
                    onClick={() => {
                      setRetentionError('')
                      setRetentionEdit({ mode: RETENTION_MODES[0], until: '' })
                    }}
                  >
                    Edit retention
                  </Button>
                </SpaceBetween>
                {retentionError && <Alert type="error">{retentionError}</Alert>}
                {retentionEdit ? (
                  <SpaceBetween size="s">
                    <Select
                      selectedOption={retentionEdit.mode}
                      onChange={({ detail }) =>
                        setRetentionEdit((held) => ({ ...held, mode: detail.selectedOption }))
                      }
                      options={RETENTION_MODES}
                      ariaLabel="Retention mode"
                    />
                    <Input
                      value={retentionEdit.until}
                      onChange={({ detail }) =>
                        setRetentionEdit((held) => ({ ...held, until: detail.value }))
                      }
                      placeholder="2030-01-01T00:00:00Z"
                      ariaLabel="Retain until"
                    />
                    <SpaceBetween direction="horizontal" size="xs">
                      <Button
                        variant="primary"
                        loading={lockSaving}
                        disabled={!retentionEdit.until.trim()}
                        onClick={saveRetention}
                      >
                        Save retention
                      </Button>
                      <Button variant="link" onClick={() => setRetentionEdit(null)}>
                        Cancel
                      </Button>
                    </SpaceBetween>
                  </SpaceBetween>
                ) : objectMeta?.retention ? (
                  <pre className="result-body">{objectMeta.retention}</pre>
                ) : (
                  <Box color="text-body-secondary">This object has no retention set.</Box>
                )}
              </div>
              <div>
                <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                  <Box variant="awsui-key-label">Legal hold</Box>
                  <Button
                    ariaLabel="Edit legal hold"
                    onClick={() => {
                      setLegalHoldError('')
                      setLegalHoldEdit(
                        objectMeta?.legal_hold?.includes('ON')
                          ? LEGAL_HOLD_OPTIONS[0]
                          : LEGAL_HOLD_OPTIONS[1],
                      )
                    }}
                  >
                    Edit legal hold
                  </Button>
                </SpaceBetween>
                {legalHoldError && <Alert type="error">{legalHoldError}</Alert>}
                {legalHoldEdit ? (
                  <SpaceBetween size="s">
                    <Select
                      selectedOption={legalHoldEdit}
                      onChange={({ detail }) => setLegalHoldEdit(detail.selectedOption)}
                      options={LEGAL_HOLD_OPTIONS}
                      ariaLabel="Legal hold"
                    />
                    <SpaceBetween direction="horizontal" size="xs">
                      <Button variant="primary" loading={lockSaving} onClick={saveLegalHold}>
                        Save legal hold
                      </Button>
                      <Button variant="link" onClick={() => setLegalHoldEdit(null)}>
                        Cancel
                      </Button>
                    </SpaceBetween>
                  </SpaceBetween>
                ) : objectMeta?.legal_hold ? (
                  <pre className="result-body">{objectMeta.legal_hold}</pre>
                ) : (
                  <Box color="text-body-secondary">This object is not under a legal hold.</Box>
                )}
              </div>
            </SpaceBetween>
          ),
        },
      ]}
    />
  )

  // The breadcrumb is the folder path: every step is a way back, and the last one is where you are.
  const folderSteps = prefix.split('/').filter(Boolean)
  const breadcrumbs = [
    { text: 'Amazon S3', href: '/s3/home' },
    { text: 'Buckets', href: '/s3/home' },
    { text: name, href: bucketLink() },
    ...folderSteps.map((step, index) => ({
      text: step,
      href: bucketLink(`${folderSteps.slice(0, index + 1).join('/')}/`),
    })),
    ...(objectOpen && objectView ? [{ text: objectView.key }] : []),
  ]

  return (
    <Shell breadcrumbs={breadcrumbs}>
      <ContentLayout header={<Header variant="h1">{name}</Header>}>
        {headMissing ? (
          <Alert type="error" header="This bucket does not exist">
            S3 answered that <strong>{name}</strong> is not there in{' '}
            {regionName(region)} <span className="mono">{region}</span>. The name may have
            been deleted, or it may belong to the wrong region.
          </Alert>
        ) : objectOpen ? (
          <Container
            header={
              <Header variant="h2" actions={objectActions}>
                {objectView ? objectView.key : 'Could not read this object'}
              </Header>
            }
          >
            {objectTab}
          </Container>
        ) : (
          <Tabs
            activeTabId={tab}
            onChange={({ detail }) => setTab(detail.activeTabId)}
            tabs={[
              { id: 'objects', label: 'Objects', content: objectsTab },
              { id: 'properties', label: 'Properties', content: propertiesTab },
              { id: 'permissions', label: 'Permissions', content: permissionsTab },
              { id: 'management', label: 'Management', content: managementTab },
              { id: 'files', label: 'File systems', content: fileSystemsTab },
              { id: 'access-points', label: 'Access Points', content: accessPointsTab },
            ]}
          />
        )}
        <Modal
          visible={Boolean(documentEdit)}
          onDismiss={() => setDocumentEdit(null)}
          header={
            `${documentEdit?.deleting ? 'Delete' : 'Edit'} ${documentEdit?.title || ''}`.trim()
          }
          size={documentEdit?.deleting ? 'medium' : 'large'}
          footer={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="xs">
                <Button variant="link" onClick={() => setDocumentEdit(null)}>
                  Cancel
                </Button>
                {documentEdit?.deleting ? (
                  <Button variant="primary" loading={saving} onClick={clearDocument}>
                    Delete
                  </Button>
                ) : (
                  <>
                    {documents[documentEdit?.label] && documentEdit?.meta?.delete && (
                      <Button loading={saving} onClick={clearDocument}>
                        Remove document
                      </Button>
                    )}
                    <Button
                      variant="primary"
                      loading={saving}
                      disabled={!documentEdit?.text?.trim()}
                      onClick={saveDocument}
                    >
                      Save
                    </Button>
                  </>
                )}
              </SpaceBetween>
            </Box>
          }
        >
          <SpaceBetween size="m">
            {documentError && <Alert type="error">{documentError}</Alert>}
            {documentEdit?.deleting ? (
              <Box>
                S3 will answer <strong>{documentEdit?.title}</strong> as not configured from
                now on. The objects in the bucket are not touched.
              </Box>
            ) : (
              <>
                <Box color="text-body-secondary" fontSize="body-s">
                  {documentEdit?.meta?.kind === 'json'
                    ? 'The bucket policy is a JSON document with a Statement.'
                    : `S3 takes this document as XML with a <${documentEdit?.meta?.root || ''}> root.`}
                </Box>
                <Textarea
                  value={documentEdit?.text || ''}
                  onChange={({ detail }) =>
                    setDocumentEdit((open) => ({ ...open, text: detail.value }))
                  }
                  rows={14}
                />
              </>
            )}
          </SpaceBetween>
        </Modal>
        <Modal
          visible={folderOpen}
          onDismiss={() => setFolderOpen(false)}
          header="Create folder"
          footer={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="xs">
                <Button variant="link" onClick={() => setFolderOpen(false)}>
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  loading={acting}
                  disabled={!folderName.trim()}
                  onClick={createFolder}
                >
                  Create folder
                </Button>
              </SpaceBetween>
            </Box>
          }
        >
          <SpaceBetween size="m">
            {error && <Alert type="error">{error}</Alert>}
            <Box>
              <Box variant="awsui-key-label">Folder name</Box>
              <Input
                value={folderName}
                onChange={({ detail }) => setFolderName(detail.value)}
                placeholder="reports/2026"
              />
            </Box>
          </SpaceBetween>
        </Modal>
        <Modal
          visible={Boolean(copying)}
          onDismiss={() => setCopying(null)}
          header={copyMode === 'move' ? 'Move object' : 'Copy object'}
          footer={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="xs">
                <Button variant="link" onClick={() => setCopying(null)}>
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  loading={saving}
                  disabled={!copyTo || !copyKey.trim()}
                  onClick={copyObject}
                >
                  {copyMode === 'move' ? 'Move' : 'Copy'}
                </Button>
              </SpaceBetween>
            </Box>
          }
        >
          <SpaceBetween size="m">
            {copyError && <Alert type="error">{copyError}</Alert>}
            <Box>
              {copyMode === 'move' ? 'Moving' : 'Copying'}{' '}
              <span className="mono">{copying}</span> from <strong>{name}</strong>.
            </Box>
            <Box>
              <Box variant="awsui-key-label">Destination bucket</Box>
              <Select
                selectedOption={copyTo}
                onChange={({ detail }) => setCopyTo(detail.selectedOption)}
                options={allBuckets.map((row) => ({
                  label: `${row.name} · ${row.region || region}`,
                  value: row.name,
                  region: row.region || region,
                }))}
                placeholder="Choose bucket"
                empty="No buckets in this account"
              />
            </Box>
            <Box>
              <Box variant="awsui-key-label">Destination key</Box>
              <Input
                value={copyKey}
                onChange={({ detail }) => setCopyKey(detail.value)}
                placeholder={`copies/${copying || ''}`}
              />
            </Box>
          </SpaceBetween>
        </Modal>
        <Modal
          visible={Boolean(rewriting)}
          onDismiss={() => setRewriting(null)}
          header={
            rewriting?.mode === 'storage-class'
              ? 'Edit storage class'
              : 'Edit server-side encryption'
          }
          footer={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="xs">
                <Button variant="link" onClick={() => setRewriting(null)}>
                  Cancel
                </Button>
                <Button variant="primary" loading={saving} onClick={rewriteObject}>
                  Save
                </Button>
              </SpaceBetween>
            </Box>
          }
        >
          <SpaceBetween size="m">
            {actionError && <Alert type="error">{actionError}</Alert>}
            <Box>
              S3 has no call that edits an object in place: the change is a copy onto
              itself, and it writes a new version of{' '}
              <span className="mono">{rewriting?.key}</span>.
            </Box>
            <Box>
              <Box variant="awsui-key-label">
                {rewriting?.mode === 'storage-class'
                  ? 'Storage class'
                  : 'Server-side encryption'}
              </Box>
              <Select
                selectedOption={(rewriting?.mode === 'storage-class'
                  ? STORAGE_CLASSES
                  : ENCRYPTION
                )
                  .map(([value, label]) => ({ value, label }))
                  .find((option) => option.value === rewriting?.value)}
                onChange={({ detail }) =>
                  setRewriting((held) => ({ ...held, value: detail.selectedOption.value }))
                }
                options={(rewriting?.mode === 'storage-class'
                  ? STORAGE_CLASSES
                  : ENCRYPTION
                ).map(([value, label]) => ({ value, label }))}
                ariaLabel={
                  rewriting?.mode === 'storage-class'
                    ? 'Storage class'
                    : 'Server-side encryption'
                }
              />
            </Box>
          </SpaceBetween>
        </Modal>
        <Modal
          visible={Boolean(aclChange)}
          onDismiss={() => setAclChange(null)}
          header="Object ACL"
          footer={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="xs">
                <Button variant="link" onClick={() => setAclChange(null)}>
                  Cancel
                </Button>
                <Button variant="primary" loading={saving} onClick={changeObjectAcl}>
                  Save
                </Button>
              </SpaceBetween>
            </Box>
          }
        >
          <SpaceBetween size="m">
            {actionError && <Alert type="error">{actionError}</Alert>}
            <Box>
              An ACL is a grant written on the object itself, in{' '}
              <span className="mono">{aclChange?.key}</span>. A bucket with Object
              Ownership set to <em>bucket owner enforced</em> has ACLs disabled and refuses
              this; S3&apos;s own sentence is shown here when it does, and the Permissions
              tab can turn ACLs back on.
            </Box>
            <RadioGroup
              value={aclChange?.value || 'private'}
              onChange={({ detail }) =>
                setAclChange((held) => ({ ...held, value: detail.value }))
              }
              items={OBJECT_ACLS.map(([value, label]) => ({ value, label }))}
            />
            {aclVersions.length > 0 ? (
              <Box>
                <Box variant="awsui-key-label">Version</Box>
                <Select
                  selectedOption={aclVersionOption}
                  onChange={({ detail }) => setAclVersion(detail.selectedOption.value)}
                  options={aclVersionOptions}
                  ariaLabel="ACL version"
                />
                <Box color="text-body-secondary" fontSize="body-s">
                  An ACL belongs to a version, and the emulator keeps them apart: a grant
                  written here applies to the version chosen.
                </Box>
              </Box>
            ) : null}
            {aclVersionsError && (
              <Box color="text-body-secondary" fontSize="body-s">
                {`Could not list this key's versions: ${aclVersionsError}`}
              </Box>
            )}
            {aclSaved && (
              <Alert type="success" header="The ACL on the object now">
                {`S3 holds ${aclSaved} on ${aclChange?.key}.`}
              </Alert>
            )}
            <Box>
              <Box variant="awsui-key-label">Current ACL</Box>
              {aclReadLoading ? (
                <Box color="text-body-secondary">Reading the object&apos;s ACL…</Box>
              ) : aclReadError ? (
                <Alert type="error" header="Could not read this object's ACL">
                  {aclReadError}
                </Alert>
              ) : aclRead ? (
                <SpaceBetween size="s">
                  <Box>
                    Owner{' '}
                    <span className="mono">
                      {aclRead.owner?.display_name || aclRead.owner?.id || dash}
                    </span>
                    {aclRead.public
                      ? ' · public: a grant names the AllUsers group'
                      : ' · not public'}
                  </Box>
                  <Table
                    items={aclRead.grants || []}
                    columnDefinitions={[
                      {
                        id: 'grantee',
                        header: 'Grantee',
                        cell: (row) => row.display_name || row.uri || row.id || row.type,
                      },
                      {
                        id: 'permission',
                        header: 'Permission',
                        cell: (row) => row.permission,
                        width: 180,
                      },
                    ]}
                    empty={
                      <Box color="text-body-secondary">S3 reports no grants on this object.</Box>
                    }
                  />
                </SpaceBetween>
              ) : null}
            </Box>
          </SpaceBetween>
        </Modal>
        <Modal
          visible={Boolean(deletingObject)}
          onDismiss={() => setDeletingObject(null)}
          header="Delete object"
          footer={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="xs">
                <Button variant="link" onClick={() => setDeletingObject(null)}>
                  Cancel
                </Button>
                <Button variant="primary" loading={saving} onClick={removeObject}>
                  Delete
                </Button>
              </SpaceBetween>
            </Box>
          }
        >
          <Box>
            Delete <strong>{deletingObject}</strong> from <strong>{name}</strong>? S3 keeps no
            undo for a plain delete.
          </Box>
        </Modal>
        <Modal
          visible={Boolean(deletingVersion)}
          onDismiss={() => setDeletingVersion(null)}
          header="Delete version"
          footer={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="xs">
                <Button variant="link" onClick={() => setDeletingVersion(null)}>
                  Cancel
                </Button>
                <Button variant="primary" loading={saving} onClick={removeVersion}>
                  Delete
                </Button>
              </SpaceBetween>
            </Box>
          }
        >
          <SpaceBetween size="s">
            <Box>
              Delete version <span className="mono">{deletingVersion?.version_id}</span> of{' '}
              <strong>{deletingVersion?.key}</strong>? The other versions of the key are
              left alone, and this one cannot be recovered.
            </Box>
            {deletingVersion?.delete_marker && (
              <Box>
                This is a delete marker: removing it puts the version beneath it back as
                the current one.
              </Box>
            )}
          </SpaceBetween>
        </Modal>
        <Modal
          visible={Boolean(uploadView)}
          onDismiss={() => setUploadView(null)}
          header="Incomplete upload"
          size="large"
          footer={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="xs">
                <Button variant="link" onClick={() => setUploadView(null)}>
                  Close
                </Button>
                <Button variant="primary" loading={saving} onClick={abortUpload}>
                  Abort upload
                </Button>
              </SpaceBetween>
            </Box>
          }
        >
          <SpaceBetween size="m">
            {partsError && <Alert type="error">{partsError}</Alert>}
            <Box>
              <Box variant="awsui-key-label">Object key</Box>
              <span className="mono">{uploadView?.key}</span>
            </Box>
            <Box>
              <Box variant="awsui-key-label">Upload ID</Box>
              <span className="mono">{uploadView?.upload_id}</span>
            </Box>
            <Table
              items={parts}
              loading={partsLoading}
              loadingText="Reading parts"
              trackBy="part_number"
              columnDefinitions={[
                { id: 'part', header: 'Part number', cell: (part) => part.part_number, width: 130 },
                {
                  id: 'size',
                  header: 'Size',
                  cell: (part) => formatSize(Number(part.size)),
                  width: 110,
                },
                { id: 'etag', header: 'ETag', cell: (part) => part.etag },
                { id: 'modified', header: 'Last modified', cell: (part) => part.modified },
              ]}
              empty={
                <Box color="text-body-secondary">This upload holds no parts yet.</Box>
              }
            />
            {partsNext && (
              <Box textAlign="center">
                <Button loading={partsMore} onClick={loadMoreParts}>
                  Load more parts
                </Button>
              </Box>
            )}
            <Box color="text-body-secondary" fontSize="body-s">
              Aborting discards every part S3 holds for this upload. Completing an upload that
              another client started is not offered here.
            </Box>
          </SpaceBetween>
        </Modal>
        <Modal
          visible={uploading}
          onDismiss={cancelUpload}
          header="Upload object"
          footer={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="xs">
                <Button
                  variant="link"
                  onClick={cancelUpload}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  loading={saving}
                  disabled={!file.length && !(newKey.trim() && newBody)}
                  onClick={upload}
                >
                  Upload
                </Button>
              </SpaceBetween>
            </Box>
          }
        >
          <SpaceBetween size="m">
            {uploadError && <Alert type="error">{uploadError}</Alert>}
            {uploadStatus && <Box color="text-body-secondary">{uploadStatus}</Box>}
            <FileUpload
              value={file}
              onChange={({ detail }) => {
                setFile(detail.value)
                setUploadError('')
                const chosen = detail.value[0]
                // The destination key follows the file name inside the folder being browsed, until the operator types one.
                if (
                  chosen &&
                  (!newKey.trim() || newKey === `${prefix}${file[0]?.name}`)
                ) {
                  setNewKey(`${prefix}${chosen.name}`)
                }
              }}
              accept="*/*"
              showFileSize
              showFileLastModified
              constraintText={`One file, up to ${formatSize(MAX_FILE)}. Above ${formatSize(MULTIPART_ABOVE)} it uploads in parts; the file's own type is stored with it.`}
              i18nStrings={{
                uploadButtonText: () => 'Choose file',
                dropzoneText: () => 'Drop a file here, or choose one',
                removeFileAriaLabel: (index) => `Remove file ${index + 1}`,
                limitShowFewer: 'Show fewer files',
                limitShowMore: 'Show more files',
                errorIconAriaLabel: 'Error',
                warningIconAriaLabel: 'Warning',
              }}
            />
            <Box>
              <Box variant="awsui-key-label">Object key</Box>
              <Input
                value={newKey}
                onChange={({ detail }) => setNewKey(detail.value)}
                placeholder="reports/2026.csv"
              />
            </Box>
            {!file.length && (
              <Box>
                <Box variant="awsui-key-label">Or type the contents</Box>
                <Textarea
                  value={newBody}
                  onChange={({ detail }) => setNewBody(detail.value)}
                  placeholder="contents"
                />
              </Box>
            )}
          </SpaceBetween>
        </Modal>
      </ContentLayout>
    </Shell>
  )
}
