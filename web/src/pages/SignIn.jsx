import { useState } from 'react'
import { Eye, EyeOff, Moon, Sun } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import Alert from '@cloudscape-design/components/alert'
import Button from '@cloudscape-design/components/button'
import Checkbox from '@cloudscape-design/components/checkbox'
import Container from '@cloudscape-design/components/container'
import Form from '@cloudscape-design/components/form'
import FormField from '@cloudscape-design/components/form-field'
import Input from '@cloudscape-design/components/input'
import Link from '@cloudscape-design/components/link'
import Popover from '@cloudscape-design/components/popover'
import RadioGroup from '@cloudscape-design/components/radio-group'
import SpaceBetween from '@cloudscape-design/components/space-between'
import { api } from '../api'
import { useThemeMode } from '../components/themeToggle'
import './signin.css'

// '' when the value is usable, otherwise the sentence the field shows. The server
// validates again — this only spares the first screen a round trip.
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const ALIAS = /^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$/

const emailProblem = (value) =>
  EMAIL.test(value.trim()) ? '' : 'That email address does not look right.'

const accountProblem = (value) => {
  const reference = value.trim()
  if (/^\d+$/.test(reference)) {
    return reference.length === 12 ? '' : 'An account ID is exactly 12 digits.'
  }
  return ALIAS.test(reference.toLowerCase())
    ? ''
    : 'Use the 12-digit account ID or the account alias.'
}

// Which account the visitor signed in with last, when they asked us to remember.
const REMEMBER_KEY = 'emuplane:signin-account'

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
  'Password reset in this deployment is local, with no mail: an administrator who can reach this account sets a new password. If you are the platform owner, run ./scripts/password.sh <username> in the service directory. Settings also offers a password change once you are signed in.'

const ACCOUNT_HELP =
  'The account ID is the 12 digits on the onboarding receipt. The alias is the short name the account was created with; either one identifies the tenancy.'

// The card every screen sits in: one narrow panel on the page background, the way
// AWS lays out its own sign-in pages.
function Card({ title, description, info, children }) {
  const { dark, toggle } = useThemeMode()
  return (
    <div className="signin">
      <div className="signin__card">
        {/* Corner utility, the way the sign-up page places its own: inside the
            card, inset from the top-right edge. */}
        <button
          type="button"
          className="signin__theme"
          onClick={toggle}
          aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
          title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {dark ? <Sun size={21} strokeWidth={2.2} aria-hidden="true" /> : <Moon size={21} strokeWidth={2.2} aria-hidden="true" />}
        </button>
        <Container>
          <div className="signin__body">
            <img className="signin__mark" src="/emuplane.png" alt="Emuplane" />
            <div className="signin__heading">
              {/* The title is rendered here rather than by Cloudscape's Header: its
                  heading root is a flex row that will not centre, and the sign-up
                  page centres its title. */}
              <h1 className="signin__title">
                {title}
                {info ? <span className="signin__info">{info}</span> : null}
              </h1>
              {description ? <div className="signin__lead">{description}</div> : null}
            </div>
            {children}
          </div>
        </Container>
      </div>
    </div>
  )
}

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

  const signUp = () => window.location.assign('/signup')

  const finish = () => {
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
      // The server decides whether this principal still owes a code; the screen
      // follows its answer rather than guessing.
      const result = await api.signIn({
        mode: userType,
        email: email.trim(),
        account: account.trim(),
        username: username.trim(),
        password,
      })
      setPassword('')
      if (result.mfa_required) {
        setStep('mfa')
        return
      }
      finish()
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
      await api.verifyMfa({ code: code.trim() })
      finish()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const notice = error ? <Alert type="error">{error}</Alert> : null

  const passwordField = (
    <SpaceBetween size="xs">
      <FormField label="Password" errorText={errors.password}>
        {/* The reveal control lives inside the field, the way AWS does it, so the
            eye lines up with the input it acts on. */}
        <div className="signin__password">
          <Input
            type={showPassword ? 'text' : 'password'}
            autoComplete="current-password"
            value={password}
            onChange={({ detail }) => setPassword(detail.value)}
          />
          <button
            type="button"
            className="signin__eye"
            onClick={() => setShowPassword((shown) => !shown)}
            aria-label={showPassword ? 'Hide password' : 'Show password'}
            aria-pressed={showPassword}
            title={showPassword ? 'Hide password' : 'Show password'}
          >
            {showPassword ? (
              <EyeOff size={16} strokeWidth={2} aria-hidden="true" />
            ) : (
              <Eye size={16} strokeWidth={2} aria-hidden="true" />
            )}
          </button>
        </div>
      </FormField>
      <div className="signin__forgot">
        <a href="/forgot">Forgot password?</a>
      </div>
    </SpaceBetween>
  )

  if (step === 'type') {
    return (
      <Card title="Sign In" description="Access your account by user type.">
        <form onSubmit={chooseType}>
          <Form>
            <SpaceBetween size="l">
              {notice}
              <div className="signin__types">
                <FormField
                  label={
                    <>
                      User type{' '}
                      <Popover
                        content={USER_TYPE_HELP}
                        header="User type"
                        dismissButton
                        size="medium"
                      >
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
              </div>

              {userType === 'root' ? (
                <FormField
                  label="Email address"
                  errorText={errors.email}
                  constraintText="username@example.com, username+one@example.com"
                >
                  <Input
                    type="email"
                    autoComplete="username"
                    value={email}
                    onChange={({ detail }) => setEmail(detail.value)}
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

              <div className="signin__actions signin__actions--row">
                <Button variant="primary" formAction="submit">
                  Next
                </Button>
                <span className="signin__or-inline">OR</span>
                <Button formAction="none" onClick={signUp}>
                  Create account
                </Button>
              </div>
            </SpaceBetween>
          </Form>
        </form>
      </Card>
    )
  }

  if (step === 'root-password') {
    return (
      <Card
        title="Root user sign in"
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
            Enter the password for <strong>{email.trim()}</strong>{' '}
            <Button
              variant="link"
              formAction="none"
              onClick={back}
              ariaLabel="use a different email address"
            >
              (not you?)
            </Button>
          </>
        }
      >
        <form onSubmit={submitCredentials}>
          <Form>
            <SpaceBetween size="l">
              {notice}
              {passwordField}
              <div className="signin__actions signin__actions--row">
                <Button variant="primary" formAction="submit" loading={busy}>
                  Sign in
                </Button>
                <Button formAction="none" onClick={back}>
                  <span className="signin__twoline">
                    Sign in to a different
                    <br />
                    account
                  </span>
                </Button>
              </div>
            </SpaceBetween>
          </Form>
        </form>
      </Card>
    )
  }

  if (step === 'iam-password') {
    return (
      <Card
        title="IAM user sign in"
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
        <form onSubmit={submitCredentials}>
          <Form>
            <SpaceBetween size="l">
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
              {passwordField}
              <div className="signin__actions signin__actions--row">
                <Button variant="primary" formAction="submit" loading={busy}>
                  Sign in
                </Button>
                <Button
                  formAction="none"
                  onClick={() => {
                    reset()
                    setUserType('root')
                    setStep('type')
                  }}
                >
                  Sign in using root user email
                </Button>
              </div>
            </SpaceBetween>
          </Form>
        </form>
      </Card>
    )
  }

  return (
    <Card
      title="Additional verification required"
      description="Your account is protected with multi-factor authentication (MFA)."
    >
      <form onSubmit={submitCode}>
        <Form>
          <SpaceBetween size="l">
            {notice}
            <div className="signin__lead">
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
            <div className="signin__actions">
              <Button variant="primary" formAction="submit" loading={busy}>
                Sign in
              </Button>
              <Button formAction="none" onClick={back}>
                Sign in to a different account
              </Button>
              <Popover
                header="Trouble signing in"
                content={RESET_HELP}
                dismissButton
                size="medium"
              >
                Trouble signing in?
              </Popover>
            </div>
          </SpaceBetween>
        </Form>
      </form>
    </Card>
  )
}
