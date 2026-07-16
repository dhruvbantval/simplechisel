/*
 * A titled content region separated by whitespace and a hairline rule — not a
 * bordered, filled card. Typography carries the hierarchy (title + optional
 * description); an optional `actions` slot holds section-level controls. This is
 * the workhorse layout primitive that keeps the dashboard free-flowing instead of
 * boxy.
 */
import styles from './Section.module.css'

export default function Section({ title, description, actions, children, className }) {
  return (
    <section className={`${styles.section} ${className ?? ''}`}>
      {(title || actions) && (
        <header className={styles.head}>
          <div className={styles.heading}>
            {title && <h2 className={styles.title}>{title}</h2>}
            {description && <p className={styles.description}>{description}</p>}
          </div>
          {actions && <div className={styles.actions}>{actions}</div>}
        </header>
      )}
      {children}
    </section>
  )
}
