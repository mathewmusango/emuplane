import React from 'react'
import Layout from '@theme/Layout'
import Link from '@docusaurus/Link'
import useDocusaurusContext from '@docusaurus/useDocusaurusContext'
import styles from './index.module.css'

const CARDS = [
  {
    title: 'Quickstart',
    to: '/docs/getting-started/quickstart',
    text: 'Two containers, one sign-in, one bucket.',
  },
  {
    title: 'Architecture',
    to: '/docs/concepts/architecture',
    text: 'The gateway, the control plane and the emulator — and which one owns which rule.',
  },
  {
    title: 'S3 coverage',
    to: '/docs/reference/s3-coverage',
    text: 'Every operation the emulator advertises, and whether the console can show or do it.',
  },
]

export default function Home() {
  const { siteConfig } = useDocusaurusContext()
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
