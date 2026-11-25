function Sidebar() {
  return (
    <aside className="sidebar">

      <div className="sidebar-header">
        <h2>KYC Portal</h2>
        <p>Document Verification</p>
      </div>

      <nav>
        <ul>
          <li>Dashboard</li>
          <li>Upload Documents</li>
          <li>Applicants</li>
          <li>Verification Queue</li>
          <li>Reports</li>
        </ul>
      </nav>

    </aside>
  )
}

export default Sidebar