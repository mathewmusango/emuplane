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
  return (
    <Layout description={siteConfig.tagline}>
      <main className={styles.hero}>
        <h1 className={styles.title}>{siteConfig.title}</h1>
        <p className={styles.tagline}>{siteConfig.tagline}</p>
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
