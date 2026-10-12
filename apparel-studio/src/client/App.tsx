import React from 'react';
import { Route, Routes, Navigate } from 'react-router-dom';
import { ProjectsPage } from './pages/ProjectsPage';
import { NewStylePage } from './pages/NewStylePage';
import { ProjectLayout } from './pages/ProjectLayout';
import { StudioPage } from './pages/StudioPage';
import { MeasurementsPage } from './pages/MeasurementsPage';
import { MaterialsPage } from './pages/MaterialsPage';
import { TechPackPage } from './pages/TechPackPage';
import { Toast } from './components/common';

export function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<ProjectsPage />} />
        <Route path="/new" element={<NewStylePage />} />
        <Route path="/p/:id" element={<ProjectLayout />}>
          <Route index element={<StudioPage />} />
          <Route path="measurements" element={<MeasurementsPage />} />
          <Route path="materials" element={<MaterialsPage />} />
          <Route path="techpack" element={<TechPackPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <Toast />
    </>
  );
}
