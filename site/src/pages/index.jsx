import React from 'react'
import Layout from '@theme/Layout'
import Link from '@docusaurus/Link'
import useBaseUrl from '@docusaurus/useBaseUrl'
import useDocusaurusContext from '@docusaurus/useDocusaurusContext'
import styles from './index.module.css'

const CARDS = [
  {
    title: 'Quickstart',
    to: '/docs/getting-started/quickstart',
    text: 'Two containers, one sign-in, one bucket.',
  },
  {
    title: 'The console',
    to: '/docs/getting-started/console',
    text: 'Every page, with a screenshot of what it reads and what it can do.',
  },
  {
    title: 'S3',
    to: '/docs/guides/s3',
    text: 'The bucket, object and access point pages, tab by tab.',
  },
  {
    title: 'Control API',
    to: '/docs/reference/control-api',
    text: 'The routes the console calls, generated from its own route table.',
  },
  {
    title: 'Coverage',
    to: '/docs/reference/s3-coverage',
    text: 'Every operation the emulator advertises, and whether the console can show or do it.',
  },
  {
    title: 'Limits',
    to: '/docs/reference/limits',
    text: 'What this console does not do, and the emulator feature behind each gap.',
  },
]

export default function Home() {
  const { siteConfig } = useDocusaurusContext()
  const screenshot = useBaseUrl('/img/console/console-home.png')
  const bannerLight = useBaseUrl('/img/banners/emuplane.png')
  const bannerDark = useBaseUrl('/img/banners/emuplane-dark.png')
  return (
    <Layout description={siteConfig.tagline}>
      <main className={styles.hero}>
        <div className={styles.banner}>
          <img
            className="banner-light"
            src={bannerLight}
            alt="Emuplane — the console, control API and gateway for AWS-compatible emulators"
            width="100%"
          />
          <img
            className="banner-dark"
            src={bannerDark}
            alt=""
            width="100%"
            aria-hidden="true"
          />
        </div>
        {/* The banner carries the title; this keeps one h1 for a reader using a screen reader. */}
        <h1 className={styles.srOnly}>{siteConfig.title}</h1>
        <div className={styles.actions}>
          <Link className={styles.primary} to="/docs/getting-started/quickstart">
            Get started
          </Link>
          <Link className={styles.secondary} to="/docs/intro">
            Read the docs
          </Link>
        </div>
        <img
          className={styles.screenshot}
          src={screenshot}
          alt="The Emuplane console home page"
        />
        <section className={styles.cards}>
          {CARDS.map((card) => (
            <Link className={styles.card} key={card.to} to={card.to}>
              <h2>{card.title}</h2>
              <p>{card.text}</p>
            </Link>
          ))}
        </section>
      </main>
    </Layout>
  )
}
