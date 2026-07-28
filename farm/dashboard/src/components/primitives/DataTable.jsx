/*
 * Config-driven table, reused by every list in the app. Encodes the skill's table
 * rules so callers get them for free:
 *   - numeric columns right-align with tabular figures (align: 'right')
 *   - categorical values render as chips via a column `render`
 *   - long values truncate (column `truncate`) with the full value on hover
 *   - inactive/secondary rows can be de-emphasized via `rowClassName`
 *   - sortable headers show a direction indicator
 *   - whole rows are clickable when `onRowClick` is given, with a hover state
 *
 * Columns: { key, header, align?, sortable?, truncate?, hint?, render?(row), sortValue?(row) }
 */
import { useMemo, useState } from 'react'
import Tooltip from './Tooltip'
import styles from './DataTable.module.css'

export default function DataTable({
  columns,
  rows,
  getRowKey,
  onRowClick,
  rowClassName,
  initialSort,
  emptyText = 'No rows.',
}) {
  const [sort, setSort] = useState(initialSort ?? null) // { key, dir }

  const sortedRows = useMemo(() => {
    if (!sort) return rows
    const col = columns.find((c) => c.key === sort.key)
    if (!col) return rows
    const value = col.sortValue ?? ((row) => row[col.key])
    const dir = sort.dir === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      const av = value(a)
      const bv = value(b)
      if (av == null) return 1
      if (bv == null) return -1
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir
      return String(av).localeCompare(String(bv)) * dir
    })
  }, [rows, sort, columns])

  const toggleSort = (key) => {
    setSort((prev) => {
      if (prev?.key !== key) return { key, dir: 'asc' }
      if (prev.dir === 'asc') return { key, dir: 'desc' }
      return null
    })
  }

  return (
    <div className={styles.scroll}>
      <table className={styles.table}>
        <thead>
          <tr>
            {columns.map((col) => {
              const isSorted = sort?.key === col.key
              const headCell = (
                <span className={styles.headInner}>
                  {col.header}
                  {col.sortable && (
                    <span className={styles.sortIcon} data-active={isSorted}>
                      {isSorted ? (sort.dir === 'asc' ? '▲' : '▼') : '↕'}
                    </span>
                  )}
                </span>
              )
              return (
                <th
                  key={col.key}
                  className={col.align === 'right' ? styles.right : undefined}
                  aria-sort={isSorted ? (sort.dir === 'asc' ? 'ascending' : 'descending') : undefined}
                >
                  {col.sortable ? (
                    <button type="button" className={styles.headBtn} onClick={() => toggleSort(col.key)}>
                      {col.hint ? <Tooltip label={col.hint} side="bottom">{headCell}</Tooltip> : headCell}
                    </button>
                  ) : col.hint ? (
                    <Tooltip label={col.hint} side="bottom">{headCell}</Tooltip>
                  ) : (
                    headCell
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {sortedRows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className={styles.empty}>
                {emptyText}
              </td>
            </tr>
          ) : (
            sortedRows.map((row) => {
              const key = getRowKey(row)
              const clickable = Boolean(onRowClick)
              return (
                <tr
                  key={key}
                  className={`${clickable ? styles.clickable : ''} ${rowClassName?.(row) ?? ''}`}
                  onClick={clickable ? () => onRowClick(row) : undefined}
                  tabIndex={clickable ? 0 : undefined}
                  onKeyDown={
                    clickable
                      ? (e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            onRowClick(row)
                          }
                        }
                      : undefined
                  }
                >
                  {columns.map((col) => {
                    const content = col.render ? col.render(row) : row[col.key]
                    return (
                      <td
                        key={col.key}
                        className={`${col.align === 'right' ? styles.right : ''} ${
                          col.truncate ? styles.truncate : ''
                        }`}
                        title={col.truncate && typeof content === 'string' ? content : undefined}
                      >
                        {content}
                      </td>
                    )
                  })}
                </tr>
              )
            })
          )}
        </tbody>
      </table>
    </div>
  )
}
