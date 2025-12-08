import Canvas3D from './components/Canvas3D';
import Sidebar from './components/Sidebar';
import Toolbar from './components/Toolbar';

function App() {
  return (
    <div className="flex h-screen bg-gray-100">
      <Sidebar />
      <main className="flex-1 relative">
        <Toolbar />
        <Canvas3D />
      </main>
    </div>
  );
}

export default App;

