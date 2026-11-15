import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import Alert from '@cloudscape-design/components/alert'
import Button from '@cloudscape-design/components/button'
import Checkbox from '@cloudscape-design/components/checkbox'
import Container from '@cloudscape-design/components/container'
import Form from '@cloudscape-design/components/form'
import FormField from '@cloudscape-design/components/form-field'
import Header from '@cloudscape-design/components/header'
import Input from '@cloudscape-design/components/input'
import Link from '@cloudscape-design/components/link'
import Popover from '@cloudscape-design/components/popover'
import RadioGroup from '@cloudscape-design/components/radio-group'
import SpaceBetween from '@cloudscape-design/components/space-between'
import { accountProblem, emailProblem, signIn, verifyMfa } from '../authStub'
import './signin.css'

// Which account the visitor signed in with last, when they asked us to remember.
const REMEMBER_KEY = 'ministack:signin-account'

const readRemembered = () => {
  try {
    return localStorage.getItem(REMEMBER_KEY) || ''
  } catch {
    return ''
  }
}

const USER_TYPES = [
  {
    value: 'root',
    label: 'Root user',
    description: 'Account owner that performs tasks requiring unrestricted access.',
  },
  {
    value: 'iam',
    label: 'IAM user',
    description: 'User within an account that performs daily tasks.',
  },
]

const USER_TYPE_HELP =
  'The root user is the email that owns the account and can do anything with it. An IAM user is a person the account created: the account ID or alias picks the tenancy, the username picks the person.'

const ROOT_HELP =
  'Root credentials belong to the account itself. Keep them for billing and for closing the account; use an IAM user for daily work.'

const IAM_HELP =
  'An IAM user belongs to exactly one account. The account ID or alias is the tenancy boundary; the username only has to be unique inside that account.'

const RESET_HELP =
  'Password reset mail is not wired yet — it arrives with the Mailbox view. Until then, an admin who can reach this account sets a new password from Settings.'

const ACCOUNT_HELP =
  'The account ID is the 12 digits on the onboarding receipt. The alias is the short name the account was created with; either one identifies the tenancy.'

export default function SignIn() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const requested = params.get('next') || '/'
  const next = requested.startsWith('/') && !requested.startsWith('//') ? requested : '/'

  const [step, setStep] = useState('type')
  const [userType, setUserType] = useState('root')
  const [email, setEmail] = useState('')
  const [account, setAccount] = useState(readRemembered)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [remember, setRemember] = useState(() => Boolean(readRemembered()))
  const [code, setCode] = useState('')
  const [errors, setErrors] = useState({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const reset = () => {
    setError('')
    setErrors({})
  }

  const back = () => {
    reset()
    setStep('type')
    setPassword('')
    setCode('')
    setShowPassword(false)
  }

  const chooseType = (event) => {
    event.preventDefault()
    reset()
    if (userType === 'root') {
      const problem = email.trim()
        ? emailProblem(email)
        : 'Enter the email address for the account.'
      if (problem) {
        setErrors({ email: problem })
        return
      }
      setStep('root-password')
      return
    }
    const problem = account.trim()
      ? accountProblem(account)
      : 'Enter the account ID or alias.'
    if (problem) {
      setErrors({ account: problem })
      return
    }
    setStep('iam-password')
  }

  const submitCredentials = async (event) => {
    event.preventDefault()
    reset()
    if (userType === 'iam' && !username.trim()) {
      setErrors({ username: 'Enter the IAM username.' })
      return
    }
    if (!password) {
      setErrors({ password: 'Enter your password.' })
      return
    }
    setBusy(true)
    try {
      await signIn({
        userType,
        email: email.trim(),
        account: account.trim(),
        username: username.trim(),
      })
      setPassword('')
      setStep('mfa')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const submitCode = async (event) => {
    event.preventDefault()
    reset()
    if (!/^\d{6}$/.test(code.trim())) {
      setErrors({ code: 'Enter the 6-digit code from your MFA device.' })
      return
    }
    setBusy(true)
    try {
      await verifyMfa({ code: code.trim() })
      try {
        if (userType === 'iam' && remember) {
          localStorage.setItem(REMEMBER_KEY, account.trim())
        } else {
          localStorage.removeItem(REMEMBER_KEY)
        }
      } catch {
        // A browser with storage denied still signs in; it just forgets.
      }
      navigate(next, { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const page = (content) => (
    <div className="signin">
      <div className="signin__card">{content}</div>
    </div>
  )

  const notice = error ? <Alert type="error">{error}</Alert> : null

  if (step === 'type') {
    return page(
      <Container
        header={
          <Header variant="h1" description="Access your AWS account by user type.">
            Sign In
          </Header>
        }
      >
        <form onSubmit={chooseType}>
          <Form
            actions={
              <SpaceBetween size="s">
                <Button variant="primary" formAction="submit" fullWidth>
                  Next
                </Button>
                <div className="signin__or">OR</div>
                <Button
                  fullWidth
                  formAction="none"
                  onClick={() => window.location.assign('/signup')}
                >
                  New to AWS? Sign up
                </Button>
              </SpaceBetween>
            }
          >
            <SpaceBetween size="m">
              {notice}
              <FormField
                label={
                  <>
                    User type{' '}
                    <Popover content={USER_TYPE_HELP} header="User type" dismissButton size="medium">
                      (not sure?)
                    </Popover>
                  </>
                }
              >
                <RadioGroup
                  value={userType}
                  onChange={({ detail }) => {
                    reset()
                    setUserType(detail.value)
                  }}
                  items={USER_TYPES}
                />
              </FormField>

              {userType === 'root' ? (
                <FormField label="Email address" errorText={errors.email}>
                  <Input
                    type="email"
                    autoComplete="username"
                    value={email}
                    onChange={({ detail }) => setEmail(detail.value)}
                    placeholder="username@example.com"
                  />
                </FormField>
              ) : (
                <FormField
                  label="Account ID (12 digits) or account alias"
                  errorText={errors.account}
                >
                  <Input
                    autoComplete="off"
                    value={account}
                    onChange={({ detail }) => setAccount(detail.value)}
                  />
                </FormField>
              )}
            </SpaceBetween>
          </Form>
        </form>
      </Container>,
    )
  }

  if (step === 'root-password') {
    return page(
      <Container
        header={
          <Header
            variant="h1"
            info={
              <Popover
                triggerType="custom"
                header="Root user"
                content={ROOT_HELP}
                dismissButton
                size="medium"
              >
                <Link variant="info">Info</Link>
              </Popover>
            }
            description={
              <>
                Enter the password for <strong>{email.trim()}</strong> (
                <Button variant="link" formAction="none" onClick={back}>
                  not you?
                </Button>
                )
              </>
            }
          >
            Root user sign in
          </Header>
        }
      >
        <form onSubmit={submitCredentials}>
          <Form
            actions={
              <SpaceBetween size="s">
                <Button variant="primary" formAction="submit" fullWidth loading={busy}>
                  Sign in
                </Button>
                <Button fullWidth formAction="none" onClick={back}>
                  Sign in to a different account
                </Button>
                <Button
                  variant="link"
                  formAction="none"
                  onClick={() => window.location.assign('/signup')}
                >
                  Create a new AWS account
                </Button>
              </SpaceBetween>
            }
          >
            <SpaceBetween size="m">
              {notice}
              <SpaceBetween size="xs">
                <FormField label="Password" errorText={errors.password}>
                  <Input
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    value={password}
                    onChange={({ detail }) => setPassword(detail.value)}
                  />
                </FormField>
                <div className="signin__row">
                  <Checkbox
                    checked={showPassword}
                    onChange={({ detail }) => setShowPassword(detail.checked)}
                  >
                    Show password
                  </Checkbox>
                  <Popover
                    header="Password reset"
                    content={RESET_HELP}
                    dismissButton
                    size="medium"
                  >
                    Forgot password?
                  </Popover>
                </div>
              </SpaceBetween>
            </SpaceBetween>
          </Form>
        </form>
      </Container>,
    )
  }

  if (step === 'iam-password') {
    return page(
      <Container
        header={
          <Header
            variant="h1"
            info={
              <Popover
                triggerType="custom"
                header="IAM user"
                content={IAM_HELP}
                dismissButton
                size="medium"
              >
                <Link variant="info">Info</Link>
              </Popover>
            }
          >
            IAM user sign in
          </Header>
        }
      >
        <form onSubmit={submitCredentials}>
          <Form
            actions={
              <SpaceBetween size="s">
                <Button variant="primary" formAction="submit" fullWidth loading={busy}>
                  Sign in
                </Button>
                <Button
                  fullWidth
                  formAction="none"
                  onClick={() => {
                    reset()
                    setUserType('root')
                    setStep('type')
                  }}
                >
                  Sign in using root user email
                </Button>
                <Button
                  variant="link"
                  formAction="none"
                  onClick={() => window.location.assign('/signup')}
                >
                  Create a new AWS account
                </Button>
              </SpaceBetween>
            }
          >
            <SpaceBetween size="m">
              {notice}
              <SpaceBetween size="xs">
                <FormField
                  label={
                    <>
                      Account ID or alias{' '}
                      <Popover
                        header="Account ID or alias"
                        content={ACCOUNT_HELP}
                        dismissButton
                        size="medium"
                      >
                        (Don&apos;t have?)
                      </Popover>
                    </>
                  }
                  errorText={errors.account}
                >
                  <Input
                    autoComplete="off"
                    value={account}
                    onChange={({ detail }) => setAccount(detail.value)}
                  />
                </FormField>
                <Checkbox
                  checked={remember}
                  onChange={({ detail }) => setRemember(detail.checked)}
                >
                  Remember this account
                </Checkbox>
              </SpaceBetween>
              <FormField label="IAM username" errorText={errors.username}>
                <Input
                  autoComplete="username"
                  value={username}
                  onChange={({ detail }) => setUsername(detail.value)}
                  placeholder="iam"
                />
              </FormField>
              <FormField label="Password" errorText={errors.password}>
                <Input
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={({ detail }) => setPassword(detail.value)}
                />
              </FormField>
              <div className="signin__row">
                <Checkbox
                  checked={showPassword}
                  onChange={({ detail }) => setShowPassword(detail.checked)}
                >
                  Show password
                </Checkbox>
                <Popover
                  header="Password reset"
                  content={RESET_HELP}
                  dismissButton
                  size="medium"
                >
                  Having trouble?
                </Popover>
              </div>
            </SpaceBetween>
          </Form>
        </form>
      </Container>,
    )
  }

  return page(
    <Container
      header={
        <Header variant="h1" description="Your account is protected with multi-factor authentication (MFA).">
          Additional verification required
        </Header>
      }
    >
      <form onSubmit={submitCode}>
        <Form
          actions={
            <SpaceBetween size="s">
              <Button variant="primary" formAction="submit" fullWidth loading={busy}>
                Sign in
              </Button>
              <Button fullWidth formAction="none" onClick={back}>
                Sign in to a different account
              </Button>
              <Popover header="Trouble signing in" content={RESET_HELP} dismissButton size="medium">
                Trouble signing in?
              </Popover>
            </SpaceBetween>
          }
        >
          <SpaceBetween size="m">
            {notice}
            <div>
              To finish signing in, enter the code from your MFA device below.
            </div>
            <FormField label="MFA code" errorText={errors.code}>
              <Input
                value={code}
                onChange={({ detail }) => setCode(detail.value)}
                placeholder="Enter code"
                autoComplete="one-time-code"
                inputMode="numeric"
              />
            </FormField>
          </SpaceBetween>
        </Form>
      </form>
    </Container>,
  )
}
